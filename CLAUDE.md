# CLAUDE.md — Skytec

Instrucciones permanentes para cualquier sesión de Claude Code en este
repositorio. Léelas completas antes de tocar código.

---

## 1. Quién soy y cómo trabajo

Soy **Oscar**, dueño del proyecto. Skytec es un negocio real con tres líneas:
servicio técnico de celulares, venta de tecnología y venta de suplementos.
Este software se entrega instalado en **una sola máquina Windows** del local.

Las decisiones de producto y de arquitectura las tomo yo. Cuando encuentres
una bifurcación de diseño, **preséntame las opciones con sus consecuencias y
espera**. No elijas por mí y me avises después.

> **A confirmar:** el remoto es `OscarPainen/skytec.git` pero los commits
> recientes vienen de `ivancalvo036-dev`. Si hay más de una persona escribiendo
> en el repo, díganmelo y ajusto las reglas de ramas de la sección 8.

### Cómo quiero que me hables

- **Lee el código real antes de proponer.** No asumas por el nombre de un
  archivo ni por lo que diga este documento. Si lo que ves contradice lo que
  está escrito acá, **detente y avísame** — el documento puede estar viejo.
- **Sin adulación.** Si mi idea tiene un problema, dímelo primero, antes de
  implementarla. Prefiero una objeción incómoda a un bug en producción.
- **Cambios quirúrgicos.** Toca lo que te pedí y nada más. Si ves algo que
  deberías arreglar de paso, anótalo y pregúntame; no lo refactorices solo.
- **Termina siempre diciéndome cómo verificar a mano** lo que hiciste. Pasos
  concretos, no "debería funcionar".
- Español de Chile. Los identificadores y comentarios del código, en español
  sin tildes ni ñ (es la convención ya establecida en el repo: `linea_negocio`,
  `categoria`, `reparacion`).

---

## 2. Qué es este sistema

Aplicación de escritorio **Python 3 + PySide6 + SQLite**. Punto de venta,
inventario, servicio técnico y agenda para un local con dos cajas.

Existe un proyecto hermano, **skytec-web**: SPA React + TypeScript + Vite
desplegada en Netlify. Es un formulario público de solicitud de reparación
que escribe en Firestore. No lee ni gestiona nada: toda la gestión ocurre en
esta app de escritorio, que consume las solicitudes vía Admin SDK.

```
main.py                      punto de entrada
ui/                          login.py, main_window.py, estilos y colores
core/                        database.py, models.py, config.py, printing.py
workers/                     printing.py (hilos)
modules/pos/                 page.py + repo.py
modules/servicio_tecnico/    page.py + repo.py
modules/inventario/          page.py + repo.py + excel.py
modules/agenda/              page.py
modules/ajustes/             page.py
scripts/
```

---

## 3. Convenciones del código — no negociables

1. **`page.py` es UI. `repo.py` es SQL.** Nunca escribas una consulta SQL en
   un `page.py`. Nunca importes widgets de Qt en un `repo.py`. Si un módulo
   nuevo necesita datos, creá su `repo.py`.
2. **Todo el dinero es `INTEGER` en pesos chilenos.** Jamás `float`, jamás
   `REAL`. Los porcentajes se calculan al momento de presentar, no se guardan.
3. **Las fechas son `TEXT`**, formato `'YYYY-MM-DD HH:MM:SS'` o `'YYYY-MM-DD'`,
   siempre en hora local (`datetime('now','localtime')`).
4. **Migraciones:** lista ordenada `MIGRATIONS` en `core/database.py`, la
   versión es el índice + 1, controlada por `PRAGMA user_version`. **Nunca
   edites una migración ya existente** — siempre agregá una nueva al final.
   Toda migración debe poder correrse dos veces sin fallar.
5. **Los colores y estilos están centralizados** (commit `c996346`). Usá los
   tokens existentes de `ui/`. **Nunca hardcodees un color en un módulo.**
6. **Sin dependencias nuevas sin preguntarme.** Cada paquete nuevo es un
   riesgo más en el empaquetado con PyInstaller. Si creés que hace falta una,
   justificá por qué no se puede resolver con lo que ya está.

---

## 4. Modelo de datos: la regla que más se rompe

**`linea_negocio` y `categoria` son cosas distintas. No las mezcles.**

| | `linea_negocio` | `categoria` |
|---|---|---|
| Valores | exactamente 3, fijos | libres, crecen con el catálogo |
| Cuáles | `reparacion`, `tecnologia`, `suplemento` | "Accesorios", "Celulares", "Proteínas"… |
| Quién los define | el diseño del sistema | yo, desde Ajustes |
| Validación | `CHECK` en la base | tabla `categorias` |
| Para qué | eje del Dashboard | desglose dentro de una línea |

Una categoría pertenece a **una** línea de negocio. Un producto tiene una
línea (obligatoria) y una categoría.

**Congelado al vender.** `venta_items` guarda `precio_unitario`,
`costo_unitario`, `linea_negocio` y `categoria` copiados del producto **en el
momento de la venta**. Nunca calcules márgenes ni reportes cruzando contra
`productos` en tiempo de consulta: si mañana cambia el costo de un producto,
el margen de las ventas viejas no puede moverse. Hay un test que protege esto;
si lo rompés, el diseño está mal, no el test.

---

## 5. Decisiones ya tomadas — no las reabras

- **Firebase: Admin SDK con service account.** Ya está confirmado, ya no hay
  que preguntarme. La web escribe con auth anónima y SDK cliente; el
  escritorio lee y actualiza con Admin SDK, que ignora las reglas de
  Firestore. Las claves `VITE_FIREBASE_*` del `.env` **no sirven** para el
  Admin SDK.
- **Sincronización por polling, no por listener.** Más simple, resiste cortes
  de red sin estado, y el volumen de solicitudes no justifica tiempo real.
- **Sin selector manual de categoría en el POS.** La línea y la categoría se
  heredan del producto. El único caso con asignación explícita son los ítems
  sin `producto_id` (servicio técnico).
- **La entidad "operación" unificada es una VISTA SQL** (`v_operaciones`), no
  una tabla. No reescribas POS, servicio técnico ni agenda para unificarlos.
- **`--onedir` en PyInstaller**, no `--onefile`.

---

## 6. Seguridad y datos — reglas duras

1. **`serviceAccount.json` nunca se commitea ni se empaqueta dentro del
   ejecutable.** Vive en el directorio de datos del usuario, referenciado por
   variable de entorno. Si la ves aparecer en un `git status`, detené todo.
2. **La base de datos nunca vive junto al ejecutable.** Va en el directorio de
   datos del sistema (`%APPDATA%\Skytec\` en Windows). Instalado en
   `Program Files`, Windows deniega la escritura y la app no arranca.
3. **Ningún fallo de sincronización, de impresión ni de respaldo puede
   impedir vender.** El POS es lo único verdaderamente crítico. Todo lo demás
   degrada en silencio y avisa, pero no bloquea.
4. **Datos de clientes:** nombre, correo y teléfono son datos personales bajo
   la Ley 21.719. No los saques de la base local, no los mandes a servicios de
   terceros, no los pongas en logs.
5. **Nunca borres datos sin respaldo previo.** Cualquier script destructivo
   pide confirmación escrita explícita, no un `y/n`.

---

## 7. Tests

No hay suite todavía; se está construyendo con pytest en `tests/`. Lo que
escribas nuevo viene con test si es lógica pura (mapeos, cálculos,
normalizaciones, agregaciones). La UI no se testea automáticamente: para eso
me das los pasos de verificación manual.

Tres tests son estructurales y no se tocan sin hablarlo conmigo:

- El costo congelado en `venta_items` no cambia cuando cambia
  `productos.costo`.
- `init_db()` corrido dos veces seguidas no falla.
- Insertar dos veces el mismo `firebase_id` deja una sola fila.

---

## 8. Ramas y commits

- Una rama por fase: `fase-N-nombre`, desde `quick-wins`.
- Cada fase termina en un estado que **funciona**, no a medio camino.
- Mensajes de commit en español, imperativo, explicando el **porqué** cuando
  no sea obvio. No `fix bug`.
- No hagas merge a `main` sin decírmelo.

---

## 9. Definición de "terminado"

Una tarea está lista cuando:

1. Corre sin errores en una base **nueva desde cero**.
2. Corre sin errores en la base **existente** (migraciones aplicadas).
3. Los tests pasan.
4. Me diste los pasos de verificación manual y los ejecuté.
5. No dejó código muerto, ni `TODO` sin ticket, ni prints de depuración.

---

## 10. Fuera de alcance para la entrega

No los implementes ni dejes stubs de ellos. Están en el backlog:

tabla de clientes y clientes recurrentes · embudo de conversión · agenda con
horas y duración de citas · utilización de agenda · flujo de caja y egresos ·
garantías · multi-sucursal · integración SII · actualización remota de la app.

Si un requerimiento que te pido necesita alguno de estos, **decímelo antes de
empezar**, no a mitad de camino.

---

## 11. Estado actual

El plan de ejecución vigente está en `docs/plan-ejecucion.md`. Consultá ahí
en qué fase estamos antes de proponer trabajo.

Si este archivo dice algo que el código contradice, **el código gana y me
avisás** para que lo actualice.
