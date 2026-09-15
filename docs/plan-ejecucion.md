# Skytec — Plan de ejecución hasta la entrega

Versión 2 · 2026-09-15 · reemplaza al plan del 2026-09-06.
Basado en el estado de avance del commit `0c3ceb1` y en el MVP de Dashboard
(`Dashboard_tipos_PoS_sistema.zip`).

Va en el repo como `docs/plan-ejecucion.md`.

---

## Qué cambió desde el 6 de septiembre

Cinco commits, todos sobre el flujo Servicio Técnico → Agenda. Tres arreglos
de refresco y UX, uno de texto, y un refactor de fondo (`e0926a1`): al aceptar
una solicitud ya no se abre la nota de venta ahí mismo, sino que salta a la
pestaña Agenda.

Ese refactor movió la nota de venta de lugar sin que nadie verificara dónde
quedó. Eso abre la pregunta de la Fase 1.5, que es la más importante de este
documento.

**Lo que no se movió:** Dashboard sigue en cero, Firebase sigue en cero, no
hay respaldos, no hay tests, y el problema de `categoria` mezclando dos
niveles sigue ahí y sigue bloqueando al Dashboard.

---

## Riesgos nuevos detectados

**1. ¿Cuándo se reconoce el ingreso de una reparación? (crítico)**

`aceptar()` crea la venta llamando a `pos.registrar_venta`. Si eso no cambió
con el refactor, el ingreso de una reparación se registra al **aceptar** —
antes de hacer el trabajo y antes de cobrar. Consecuencias:

- Una reparación aceptada que el cliente nunca retira (`no_retirada`) ya está
  contada como venta.
- El Dashboard va a informar ingresos que no entraron a la caja.
- Cuando el número no cuadre con el banco a fin de mes, el error va a estar
  a semanas de distancia y va a ser carísimo de rastrear.

No lo arregles antes de diagnosticarlo. Ver Fase 1.5.

**2. El límite de 15 en la Agenda.** `0c3ceb1` resolvió que las filas
desaparecieran al cambiar de estado, pero mostrando "los últimos 15 servicios
agendados". Con volumen real vuelven a desaparecer, por otra razón y más
difícil de diagnosticar. El corte debe ser por estado y fecha, no por un
número mágico.

**3. El CLAUDE.md del repo está desalineado.** Dice que category tags y
Ajustes están pendientes cuando ya están hechos, y sigue bloqueando el trabajo
de Firebase esperando una confirmación que ya diste. Reemplazalo por el
CLAUDE.md nuevo antes de empezar cualquier fase.

---

## Orden de ejecución

| Fase | Qué | Est. | Por qué en ese orden |
|---|---|---|---|
| 0 | Blindaje operacional | 0,5 d | Sin esto, un corte de luz borra el negocio |
| 0.B | Spike de empaquetado | 2 h | Si falla, cambia todo el plan de Firebase |
| 1 | Migración v4 (esquema) | 1–2 d | Bloquea Dashboard y Firebase |
| 1.5 | Auditoría del flujo de venta | 0,5 d | Define qué significa "ingreso" |
| 2 | Dashboard | 2–3 d | Tu prioridad #1 |
| 3 | Firebase | 2–3 d | Contrato ya cerrado, es ejecución |
| 4 | Empaquetado y entrega | 1–2 d | — |

Total: unos 10 días de trabajo efectivo.

**Regla:** una fase por sesión de Claude Code, una rama por fase, y no avanzás
si el criterio de aceptación no pasa.

---

## Bloque de contexto

> Con el CLAUDE.md nuevo en el repo, Claude Code ya tiene el contexto
> permanente. Al inicio de cada sesión basta con:

```
Leé CLAUDE.md y docs/plan-ejecucion.md completos antes de responder.
Vamos a hacer la FASE <N>. Confirmame en qué estado está el repo
(rama, HEAD, user_version de la base) y después pegame tu plan de
ataque ANTES de tocar código.
```

---

# FASE 0 — Blindaje operacional

```
FASE 0 — BLINDAJE OPERACIONAL

Tres defectos que hoy garantizan pérdida de datos o falla de arranque en el
equipo del cliente. No toques ninguna funcionalidad de negocio.

--- 1. DB_PATH es una ruta de escritura imposible en producción

Hoy DB_PATH apunta a la carpeta del proyecto. Instalado en
C:\Program Files\Skytec\, Windows deniega la escritura y la app no arranca.

  a) Módulo nuevo core/paths.py con app_data_dir() -> Path:
       Windows: %APPDATA%\Skytec\
       macOS:   ~/Library/Application Support/Skytec/
       Linux:   $XDG_DATA_HOME/skytec/ o ~/.local/share/skytec/
     A mano con sys.platform. NO uses QStandardPaths: core/ debe poder
     importarse sin QApplication viva. Crea el directorio si no existe.
  b) core/database.py: DB_PATH = app_data_dir()/"skytec.db", MANTENIENDO el
     override por variable de entorno SKYTEC_DB con la misma prioridad.
  c) core/config.py: skytec_config.json también se muda a app_data_dir().
  d) Migración one-shot: si hay un skytec.db en la raíz del proyecto y no hay
     uno en el destino, copialo al iniciar y dejalo en el log. Solo copiar,
     nunca borrar el original.

--- 2. journal_mode = delete

Un corte de luz durante una venta puede corromper el archivo.
  a) Al inicializar: PRAGMA journal_mode = WAL. Verificá que devuelva 'wal';
     si no, advertencia clara en el log.
  b) En get_connection(), sumado al foreign_keys = ON que ya está:
       PRAGMA synchronous = NORMAL;
       PRAGMA busy_timeout = 5000;
  c) Con WAL aparecen skytec.db-wal y skytec.db-shm. Verificá que .gitignore
     los cubra y que nada que copie o mueva la base los ignore.

--- 3. Cero respaldos

Módulo nuevo core/backup.py:
  a) hacer_backup_diario() -> Path | None
     - Destino app_data_dir()/"backups"/f"skytec-{YYYYMMDD}.db"
     - Si ya existe el del día, no hace nada y devuelve None.
     - VACUUM INTO, no shutil.copy: es consistente con WAL y compacta.
       Ojo: VACUUM INTO falla si el destino ya existe.
     - Rotación: conserva los 15 más recientes.
     - NUNCA lanza excepción hacia arriba. Un respaldo fallido no puede
       impedir que el negocio abra la caja.
  b) Llamada desde main.py después de init_db() y antes de mostrar la
     ventana.
  c) Respaldá también skytec_config.json, con shutil.copy2 y misma rotación.

--- TESTS
Bloques `if __name__ == "__main__":` en core/paths.py y core/backup.py:
ruta absoluta y existente; el respaldo se crea la primera vez y devuelve None
la segunda; la rotación deja exactamente 15 de 20.

--- CRITERIO DE ACEPTACIÓN (mostrame la salida de cada punto)
1. La app arranca y crea la base en el directorio de datos del sistema.
2. PRAGMA journal_mode devuelve 'wal' sobre la base real.
3. Primer arranque del día crea el respaldo; el segundo no lo duplica.
4. Con SKYTEC_DB=/tmp/test.db la app usa esa base.
5. Login, una venta en el POS y una solicitud de servicio técnico siguen
   funcionando igual que antes.
```

---

# FASE 0.B — Spike de empaquetado

```
FASE 0.B — SPIKE DE EMPAQUETADO (experimento desechable)

Necesito saber HOY si PySide6 + firebase-admin + PyInstaller se puede
empaquetar, antes de escribir los tres días de código que dependen de
firebase-admin. firebase-admin arrastra grpcio, que es la causa más común de
fallos de empaquetado con Qt.

No lo integres al proyecto. Directorio spike/ agregado a .gitignore.

  1. venv limpio con PySide6, firebase-admin, pyinstaller.
  2. spike_app.py de ~30 líneas: QMainWindow con un botón que importa
     firebase_admin y muestra firebase_admin.__version__ en un QLabel. NO
     necesita conectarse a Firebase: lo que pruebo es que el import funcione
     DENTRO del ejecutable empaquetado.
  3. Empaquetar con --onedir y ejecutar el binario.

Si falla, probá en orden y documentá cuál funcionó:
  --collect-all grpc · --collect-all google.cloud ·
  --hidden-import grpc._cython.cygrpc · --collect-data certifi ·
  archivo .spec explícito

ENTREGABLE (este sí se commitea): docs/empaquetado-hallazgos.md con
¿funcionó?, los flags o el .spec exactos, tamaño del build, advertencias
aunque el build funcione, y versiones de PySide6, firebase-admin, grpcio y
PyInstaller.

IMPORTANTE: desarrollo en macOS pero entrego en Windows, y PyInstaller no
hace cross-compilation. Si podés probarlo en Windows, hacelo. Si no, dejá
escrito explícitamente que falta repetirlo en Windows antes de la Fase 4.
```

---

# FASE 1 — Migración v4: separar línea de negocio de categoría

```
FASE 1 — MIGRACIÓN v4: SEPARAR LÍNEA DE NEGOCIO DE CATEGORÍA

--- DIAGNÓSTICO

El campo `categoria` hace hoy dos trabajos incompatibles, y por eso hay tres
fuentes de verdad que no coinciden:
  productos.categoria    -> "Accesorios", "Protección", "tecnologia"
  venta_items.categoria  -> NULL, "Accesorios", "Protección", "reparacion"
  skytec_config.json     -> "reparacion", "tecnologia", "Suplementos"
Un GROUP BY hoy daría 4 o 5 grupos en vez de 3, y "Accesorios" no calzaría en
ninguna línea. Esto bloquea el Dashboard.

Leé la sección 4 del CLAUDE.md antes de empezar: ahí está la regla completa.

--- CONTEXTO DE DATOS

La base tiene SOLO datos de prueba (8 ventas, 9 ítems, 3 productos, con
basura tipo "fasf"). Es descartable. NO escribas backfills, NO mantengas
compatibilidad hacia atrás, NO preserves filas. Al final reseteamos.

--- ESQUEMA (migración v4, agregada al final de MIGRATIONS)

1. Tabla nueva:
     CREATE TABLE categorias (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       nombre TEXT NOT NULL UNIQUE COLLATE NOCASE,
       linea_negocio TEXT NOT NULL
         CHECK (linea_negocio IN ('reparacion','tecnologia','suplemento')),
       activa INTEGER NOT NULL DEFAULT 1
     );
   Semilla: al menos una categoría por línea, para que POS e inventario nunca
   queden sin opciones. Ej: ('Reparaciones','reparacion'),
   ('Accesorios','tecnologia'), ('Celulares','tecnologia'),
   ('Suplementos','suplemento').

2. productos: agregar
     linea_negocio TEXT NOT NULL DEFAULT 'tecnologia'
       CHECK (linea_negocio IN ('reparacion','tecnologia','suplemento'))
   `categoria TEXT` se mantiene como texto libre (no FK), pero la UI solo
   ofrece valores de la tabla categorias. Razón: una FK obligaría a reescribir
   modules/inventario/excel.py y toda la carga masiva; no compensa.

3. venta_items: agregar
     linea_negocio TEXT NOT NULL DEFAULT 'tecnologia' CHECK (...)
     costo_unitario INTEGER NOT NULL DEFAULT 0

4. ventas: agregar
     origen TEXT NOT NULL DEFAULT 'pos'
       CHECK (origen IN ('pos','web','agenda'))
   'pos' = mostrador · 'web' = nace de solicitud con origen='web' ·
   'agenda' = nace de solicitud manual.

SOBRE SQLite: ALTER TABLE ADD COLUMN tiene restricciones con CHECK y NOT
NULL. Como la base es descartable, usá el patrón de reconstrucción de tabla
documentado por SQLite (crear nueva con el esquema final, copiar, DROP,
RENAME) para productos y venta_items. CUIDADO: la reconstrucción necesita
PRAGMA foreign_keys = OFF, y get_connection() lo pone en ON. Manejalo
explícitamente dentro de la migración y dejalo en ON al salir. Todo dentro de
una transacción.

--- LISTA DE CATEGORÍAS EN JSON

skytec_config.json tiene la clave "categorias" con
["reparacion","tecnologia","Suplementos"]. Esos son valores de LÍNEA, no de
categoría: NO los migres a la tabla categorias. Eliminá la clave del JSON y
de los DEFAULTS de core/config.py.

--- CÓDIGO

modules/pos/repo.py (registrar_venta):
  - Ítems con producto_id: copiar productos.costo -> costo_unitario,
    productos.linea_negocio -> linea_negocio, productos.categoria ->
    categoria, todo en el mismo SELECT, congelado al insertar.
  - Ítems sin producto_id: recibir linea_negocio en el dict del ítem. Si
    falta, lanzar error. Sin default silencioso.
  - movimientos_stock: hoy inserta la salida por venta con costo_unitario
    NULL. Rellenalo con el mismo costo.
  - ventas.origen = 'pos' en ventas directas.

modules/servicio_tecnico/repo.py (aceptar):
  - linea_negocio = 'reparacion' en el ítem.
  - costo_unitario = 0 con un TODO: el servicio técnico no tiene costo de
    repuestos modelado. No inventes un campo nuevo.
  - ventas.origen = 'web' si solicitud.origen == 'web', si no 'agenda'.

modules/inventario/:
  - page.py: al crear o editar producto, selector OBLIGATORIO de línea (3
    opciones fijas) y selector de categoría filtrado por la línea elegida.
    Sin opción vacía.
  - excel.py: plantilla e importación con columna linea_negocio. Filas con
    línea inválida o vacía se rechazan con el número de fila en el mensaje.
    Nunca importes con default silencioso.

modules/ajustes/page.py:
  - La sección "Categorías" lee y escribe en la tabla categorias, no en el
    JSON. Al agregar, pide nombre + línea de negocio.
  - Mantené el guardrail de borrado que ya existe. Si la categoría está en
    uso, ofrecé DESACTIVARLA (activa=0) en vez de borrarla: desaparece de los
    selectores sin romper el histórico.
  - NO agregues UI para editar las líneas de negocio. Son fijas por diseño.

--- SCRIPT DE RESET

scripts/reset_db.py que: pide confirmación escribiendo el texto RESET (no
y/n); hace respaldo previo con core/backup; borra ventas, venta_items,
movimientos_stock, solicitudes_reparacion, servicios_tecnicos y productos;
conserva usuarios, config y categorias; reinicia sqlite_sequence.

--- LIMPIEZA

Borrá scripts/backfill_categoria_venta_items.py: fue escrito para el modelo
viejo de categoría única y nunca se corrió con --apply.

--- TESTS (creá tests/ con pytest; agregalo a requirements.txt en un bloque
    comentado de desarrollo)
  - test_migraciones.py: base temporal vacía llega a user_version = 4 con
    todas las columnas esperadas; init_db() dos veces seguidas no falla.
  - test_pos_repo.py: vender un producto de costo 1000 y precio 1500 deja
    venta_items con costo_unitario=1000, linea_negocio heredada, y
    ventas.origen='pos'.
  - test_margen.py: cambiar productos.costo a 9999 DESPUÉS de la venta no
    altera el costo_unitario guardado. Este test protege la decisión central
    de la fase.

--- CRITERIO DE ACEPTACIÓN
1. Base nueva desde cero llega a user_version = 4 sin errores.
2. Los tests pasan.
3. Creo un producto eligiendo línea y categoría, lo vendo, y la fila de
   venta_items tiene costo_unitario y linea_negocio correctos.
4. Ajustes permite agregar y desactivar categorías, y no deja borrar una en
   uso.
5. La importación por Excel rechaza filas sin línea válida.
6. Un ciclo de servicio técnico completo genera una venta con origen='agenda'
   y linea_negocio='reparacion'.
```

---

# FASE 1.5 — Auditoría del flujo de venta y agenda

**Esta fase es diagnóstico primero. No escribas código hasta que yo apruebe el
diagnóstico.**

```
FASE 1.5 — AUDITORÍA DEL FLUJO SERVICIO TÉCNICO -> AGENDA -> VENTA

El refactor e0926a1 movió la nota de venta de lugar y nadie verificó dónde
quedó. Antes de construir el Dashboard necesito saber exactamente en qué
momento se registra un ingreso, porque de eso depende que los números del
Dashboard signifiquen algo.

PRIMERO DIAGNOSTICÁ. No cambies nada hasta que yo apruebe.

--- PREGUNTAS A RESPONDER CON CÓDIGO A LA VISTA

1. ¿En qué punto exacto del flujo se llama a pos.registrar_venta() para una
   reparación? Mostrame la traza completa: qué acción del usuario la dispara,
   en qué archivo y línea.
2. ¿Sigue siendo al ACEPTAR la solicitud? Si es así: una reparación aceptada
   que el cliente nunca retira (estado 'no_retirada') queda contada como
   venta. Confirmá si eso es lo que pasa hoy.
3. ¿Qué pasa si una solicitud aceptada se cancela o se marca 'no_retirada'?
   ¿Se revierte la venta? ¿Se revierte el movimiento de stock? ¿O queda todo
   registrado?
4. ¿Se puede aceptar dos veces la misma solicitud y generar dos ventas?
   Probalo de verdad, no lo deduzcas.
5. ¿Dónde quedó la nota de venta después del refactor? ¿Desde qué pantallas
   se puede emitir? ¿Hay algún camino del flujo donde el servicio se complete
   sin que se pueda imprimir la nota?
6. servicios_tecnicos.estado y solicitudes_reparacion.estado son dos columnas
   distintas. ¿Cuál manda? ¿Pueden quedar desincronizadas? El código solo
   escribe 'aceptada' en la primera: ¿la otra sirve para algo?
7. El estado 'vencida' está en el CHECK pero nunca se escribe: se calcula al
   vuelo en repo._fila. ¿Hay algún lugar que lo lea de la base y falle?
8. La Agenda ahora muestra "los últimos 15 servicios agendados". ¿Es un
   LIMIT 15 literal? Con volumen real, ¿qué servicios dejan de verse?

--- ENTREGABLE DEL DIAGNÓSTICO

Un documento docs/flujo-venta.md con:
  - Diagrama de texto del flujo completo: solicitud -> aceptar -> agenda ->
    estados -> venta -> nota de venta, marcando en qué paso se escribe cada
    tabla.
  - La lista de agujeros encontrados, ordenada por impacto en los números.
  - Para cada uno, tu recomendación con el trade-off, sin implementarla.

--- DESPUÉS DE QUE YO APRUEBE, LOS ARREGLOS PROBABLES

(No los hagas sin mi OK, están acá para que dimensiones.)
  a) Que el ingreso se reconozca al COMPLETAR el servicio, no al aceptar.
     Es el cambio correcto contablemente y el que más impacta al Dashboard.
  b) Idempotencia: aceptar dos veces no puede generar dos ventas.
  c) Reversión o anulación cuando un servicio queda 'no_retirada'.
  d) El corte de la Agenda por estado y ventana de fechas, no por LIMIT 15.
  e) Sincronizar o eliminar la columna redundante de estado.

--- CRITERIO DE ACEPTACIÓN
El documento existe, yo lo leí, y decidimos juntos qué se arregla antes del
Dashboard y qué después.
```

---

# FASE 2 — Dashboard

El MVP del zip trae tres variantes. Análisis antes del prompt:

| Variante | Qué es | Veredicto |
|---|---|---|
| **1a** — Panel por período | semana/mes/año con comparativo, KPIs, ventas por línea, participación | **Esto es el Dashboard v1.** Todo computable con el esquema v4 |
| **1b** — Vista operativa en vivo | turno de hoy, caja por caja, feed de últimas ventas, ventas por hora | Parcial. `pos_origen` permite el corte por caja, pero "turno abierto/cerrado" no está modelado, y el feed en vivo agrega complejidad que no paga |
| **1c** — Vista anual comparada | 2026 vs 2025, mapa de calor semanal, mezcla anual | **Imposible a la entrega.** No vas a tener un año de historia. Reevaluar en 2027 |

De 1b vale la pena rescatar **una sola cosa**: el corte por caja. Es barato
(`ventas.pos_origen` ya existe) y en un local de dos cajas es información
operativa real. El feed en vivo y las ventas por hora, no.

El screenshot del zip muestra ventas, N° de ventas y ticket promedio, **sin
margen**. Como la Fase 1 agrega `costo_unitario`, el margen pasa a ser gratis
y es el indicador que más te va a decir del negocio. Lo incluyo.

```
FASE 2 — DASHBOARD

Depende de la Fase 1 (verificá user_version = 4) y de las decisiones de la
Fase 1.5 sobre cuándo se reconoce un ingreso.

--- ALCANCE

Cinco indicadores, por línea de negocio, con comparación contra el período
anterior equivalente:
  1. Ventas (ingresos)
  2. Margen bruto ($ y %)
  3. N° de operaciones
  4. Ticket promedio
  5. Participación porcentual de cada línea

Más un corte por caja (ventas.pos_origen), que en un local de dos cajas es
información operativa real y sale gratis.

FUERA DE ALCANCE, no implementes ni dejes stubs: feed de ventas en vivo,
ventas por hora, turnos de caja, comparación año contra año, mapa de calor
semanal, clientes recurrentes, embudo de conversión, utilización de agenda,
flujo de caja. No existe el modelo de datos, o no habrá historia suficiente
a la entrega.

--- PIEZA CENTRAL: LA VISTA v_operaciones (migración v5)

Antes de escribir UI. La idea es que el Dashboard consulte UNA sola cosa con
forma uniforme, sin reescribir POS ni servicio técnico.

  CREATE VIEW v_operaciones AS
  SELECT
    vi.id                           AS id_operacion,
    v.fecha                         AS fecha,
    date(v.fecha)                   AS dia,
    strftime('%Y-%m', v.fecha)      AS periodo,
    vi.linea_negocio                AS linea_negocio,
    COALESCE(vi.categoria,'Sin categoría') AS categoria,
    v.origen                        AS origen,
    v.pos_origen                    AS caja,
    COALESCE(vi.descripcion, p.nombre,'Sin descripción') AS descripcion,
    vi.cantidad                     AS cantidad,
    vi.subtotal                     AS monto,
    vi.costo_unitario * vi.cantidad AS costo,
    vi.subtotal - (vi.costo_unitario * vi.cantidad) AS margen,
    v.id                            AS venta_id,
    vi.producto_id                  AS producto_id
  FROM venta_items vi
  JOIN ventas v ON v.id = vi.venta_id
  LEFT JOIN productos p ON p.id = vi.producto_id;

Verificá esta definición contra el esquema real antes de aplicarla; si algo
no calza, decímelo en vez de improvisar.

Nota de diseño: no hace falta unir servicios_tecnicos porque aceptar() ya
crea la venta y sus venta_items — todo el ingreso pasa por venta_items.
CONFIRMALO leyendo el código y el resultado de la Fase 1.5 antes de darlo por
bueno.

Índices en la misma migración:
  CREATE INDEX IF NOT EXISTS idx_ventas_fecha ON ventas(fecha);
  CREATE INDEX IF NOT EXISTS idx_venta_items_venta ON venta_items(venta_id);
  CREATE INDEX IF NOT EXISTS idx_venta_items_linea ON venta_items(linea_negocio);

--- MÓDULO

modules/dashboard/ con repo.py y page.py. TODO el SQL en repo.py.

repo.py — funciones que devuelven dicts, nunca filas crudas:
  resumen_periodo(desde, hasta)        -> los 5 KPIs totales
  por_linea_negocio(desde, hasta)      -> una fila por línea
  por_categoria(linea, desde, hasta)   -> desglose dentro de una línea
  por_caja(desde, hasta)               -> corte por pos_origen
  serie_diaria(desde, hasta)           -> para el gráfico de barras

Robustez, no negociable:
  - División por cero: sin operaciones, ticket promedio y % de margen dan 0,
    no None ni excepción.
  - Un período sin datos devuelve la estructura completa en ceros, no lista
    vacía. La UI no debe manejar dos formas distintas.
  - Las TRES líneas aparecen SIEMPRE en por_linea_negocio, aunque no tengan
    ventas. Un cero es información; una fila ausente es un bug visual.
  - Dinero en INTEGER. Los porcentajes se calculan al presentar.

--- DISEÑO VISUAL

Te adjunto un MVP en HTML (variante "1a") como referencia de ESTRUCTURA y
JERARQUÍA, no de colores.

REGLA DURA: leé primero ui/ (los estilos y colores están centralizados desde
el commit c996346) y usá esos tokens. NO hardcodees un solo color en
modules/dashboard/. Si el MVP usa un color que no existe en los tokens,
agregalo al módulo central de colores, no al dashboard.

Referencia del MVP, para mapear a los tokens existentes:
  fondo general    #08080a       tarjetas     #111113
  borde            rgba(255,255,255,.08)      radio 14px
  texto            #f4f4f5       texto tenue  rgba(255,255,255,.5)
  reparaciones     #2CA86E (verde)
  tecnologia       #3B82E6 (azul)
  suplementos      #C9821F (ámbar)
Los tres colores de línea de negocio SÍ importan: son el código visual del
Dashboard y deben ser consistentes en toda la app.

Layout, de arriba hacia abajo:
  1. Encabezado: título "Dashboard" + selector de período a la derecha
     (Semana / Mes / Año / Todo). Por defecto Mes.
  2. Fila de KPIs grandes: Ventas, Margen, N° de ventas, Ticket promedio.
     Número grande, etiqueta chica arriba, y debajo la variación contra el
     período anterior equivalente (flecha + porcentaje). Verde si mejora,
     rojo si empeora. OJO: un margen que baja es rojo aunque las ventas
     suban.
  3. "Ventas por línea de negocio": tres tarjetas, una por línea, cada una
     con su color, monto, porcentaje de participación, N° de ítems y una
     barra de progreso proporcional.
  4. "Participación de cada línea": barras horizontales apiladas con el
     porcentaje a la derecha.
  5. Desglose por categoría de la línea seleccionada, en tabla.
  6. Corte por caja, en tabla chica.

Tipografía y espaciado: seguí lo que ya usa la app. El MVP usa Plus Jakarta
Sans; si la app usa otra, gana la de la app. La consistencia importa más que
el MVP.

--- SIN DEPENDENCIAS NUEVAS

Nada de QtCharts, matplotlib ni pyqtgraph. Las barras se dibujan con QFrame
de ancho proporcional o QProgressBar estilizado. Cada dependencia es un
riesgo más en el empaquetado, y para cinco indicadores no se justifica.

--- INTEGRACIÓN

Agregalo a ui/main_window.py siguiendo el patrón de los módulos existentes.
Que sea la vista por defecto al iniciar sesión.

--- TESTS
  - test_dashboard_repo.py: con una base sembrada con ventas conocidas en dos
    meses distintos, cada función devuelve los números exactos esperados.
    Calculá los valores esperados a mano en el test, NO con la misma consulta
    que estás probando.
  - Caso borde explícito: período sin ninguna venta devuelve ceros en las
    tres líneas, sin excepción.

--- CRITERIO DE ACEPTACIÓN
1. Con la base vacía el Dashboard abre y muestra ceros, sin errores.
2. Registro tres ventas de líneas distintas y los cinco indicadores cuadran
   con el cálculo hecho a mano.
3. El margen refleja el costo congelado: si cambio productos.costo después de
   vender, el Dashboard no se mueve.
4. Cambiar de período recalcula y la comparación es correcta.
5. Visualmente es indistinguible del resto de la app: mismos colores, misma
   tipografía, mismo espaciado.
6. Los tests pasan.
```

---

# FASE 3 — Firebase

```
FASE 3 — SINCRONIZACIÓN CON FIREBASE

El enfoque ya está decidido (CLAUDE.md sección 5): Admin SDK con service
account. No hay nada que preguntarme sobre eso.

--- CONTRATO (verificado en el repo skytec-web)

Colección `solicitudes/{autoId}`:
  modelo_telefono          string
  cliente_nombre           string
  cliente_email            string
  cliente_telefono         string    INTERNACIONAL, puede NO llevar +56
  tipo_servicio            string    lista fija de 6
  tipo_servicio_detalle    string    "" salvo tipo_servicio == "Otro / a evaluar"
  fecha_entrega_solicitada timestamp mediodía local del día elegido
  estado                   string    SIEMPRE "nueva" al crear
  creado_en                timestamp serverTimestamp

El ID del documento NO va dentro del documento: es lo que se guarda en
solicitudes_reparacion.firebase_id.

Lista fija de tipo_servicio: "Cambio de pantalla", "Cambio de batería",
"Reparación de puerto de carga", "Problema de software", "Daño por líquido",
"Otro / a evaluar".

Flujo: la web crea con estado "nueva" -> el escritorio baja las "nueva",
crea la solicitud local, y marca el documento remoto como "sincronizada" ->
la web nunca vuelve a tocarlo.

--- CREDENCIALES
  - Descomentá firebase-admin>=6.5 en requirements.txt.
  - Service account leída desde SKYTEC_FIREBASE_CREDENTIALS, con default
    app_data_dir()/"serviceAccount.json".
  - NUNCA dentro del ejecutable, NUNCA commiteada. Agregá serviceAccount.json
    y *serviceAccount*.json a .gitignore y documentá la ruta en .env.example.
  - Si el archivo no existe, la app arranca igual con la sincronización
    apagada y el indicador en "sin conexión". Que falte la credencial NO
    puede impedir vender.

--- MIGRACIÓN v6
  solicitudes_reparacion: agregar tipo_servicio_detalle TEXT y
  sincronizado_en TEXT.
  NO toques el CHECK de `estado`: 'nueva' y 'sincronizada' son estados del
  lado Firestore, no del lado local. El mapeo se hace al insertar.

--- MAPEO (función pura, módulo propio, con tests)

mapear_solicitud_firestore(doc_id, data) -> dict. Pura: sin I/O, sin base.
  estado "nueva"                        -> 'pendiente'
  fecha_entrega_solicitada (Timestamp)  -> TEXT 'YYYY-MM-DD' hora local
  creado_en (Timestamp)                 -> TEXT 'YYYY-MM-DD HH:MM:SS' local
  doc_id                                -> firebase_id
  (fijo)                                -> origen = 'web'
  tipo_servicio_detalle                 -> columna nueva, tal cual
  cliente_telefono                      -> normalizar (abajo)
Campos faltantes o nulos: string vacío, nunca None que rompa un NOT NULL.
Campos inesperados en el documento: ignoralos, no falles.

--- NORMALIZACIÓN DE TELÉFONO (bug real)

modules/servicio_tecnico/repo.py arma https://wa.me/{digits} quitando lo no
numérico. Como la web acepta números internacionales que pueden venir sin
+56, un número chileno local sale mal.

normalizar_telefono(raw) -> str:
  - Ya viene con + y código de país: conservá los dígitos tal cual.
  - 9 dígitos empezando con 9 (móvil chileno): anteponé 56.
  - 8 dígitos (fijo chileno): anteponé 562.
  - No reconocido: devolvé los dígitos sin tocar y registrá advertencia.
    Nunca lances excepción.
Aplicala en la ingesta Y en el formulario manual, y usala para el link de
WhatsApp.

--- WORKER

workers/sync.py siguiendo el patrón de workers/printing.py (QThread).
  - Polling cada 60 s, configurable en config (clave sync_intervalo_segundos).
  - Query: collection('solicitudes').where('estado','==','nueva')
    .order_by('creado_en').limit(50)
  - ORDEN DE OPERACIONES, crítico: primero INSERT local, DESPUÉS marcar el
    documento remoto. Nunca al revés. Si el proceso muere entre ambos pasos,
    el siguiente ciclo relee el documento y el INSERT OR IGNORE sobre
    firebase_id UNIQUE lo descarta sin duplicar. Al revés perderías la
    solicitud para siempre.
  - INSERT OR IGNORE apoyado en el UNIQUE. NO consultes "¿ya existe?" antes:
    eso es una condición de carrera y el UNIQUE ya lo resuelve.
  - Al marcar remoto: estado='sincronizada', sincronizado_en=SERVER_TIMESTAMP.
  - Errores de red: backoff exponencial 60s/120s/240s, techo 15 min. Al
    recuperar, vuelve al intervalo normal.
  - El worker NUNCA lanza excepción al hilo de UI ni cierra la app.
  - Señales: conexion_cambiada(bool), solicitudes_recibidas(int),
    error_sync(str).

--- UI
  - ui/main_window.py ya tiene set_estado_conexion(online) sin llamador
    (~línea 154). Conectalo a conexion_cambiada.
  - Al llegar solicitudes, refrescá Servicio Técnico si está abierto. NO
    abras diálogos ni robes el foco: puede haber una venta en curso.
  - Contador discreto de solicitudes nuevas sin revisar en el item de
    navegación.

--- TESTS
  - test_mapeo.py: documento completo, con campos faltantes, con "Otro / a
    evaluar" y detalle, y conversión de timestamps con zona horaria.
  - test_normalizar_telefono.py: +56 9 1234 5678 · 912345678 · 9 1234 5678 ·
    +1 555 123 4567 · basura.
  - test_idempotencia.py: insertar dos veces el mismo firebase_id deja una
    sola fila.
  El worker no se testea contra Firebase real. Separá la lógica pura de la
  I/O para que lo testeable quede testeado.

--- PASOS MANUALES MÍOS (listámelos al final, no los intentes)
  1. Confirmar en consola: auth anónima habilitada, Firestore creado en modo
     producción, firestore.rules publicadas.
  2. Dominio de Netlify en Firebase Auth -> Authorized domains. Sin esto el
     login anónimo falla en producción.
  3. Generar la service account y ponerla en el directorio de datos.
  4. RECOMENDADO: activar App Check con reCAPTCHA v3. Hoy
     `allow create: if request.auth != null` con auth anónima permite que
     cualquiera cree sesiones ilimitadas e inunde la colección con
     solicitudes falsas, consumiendo cuota.

--- CRITERIO DE ACEPTACIÓN
1. Sin serviceAccount.json la app arranca normal, indicador en "sin
   conexión", todo lo demás funciona.
2. Con credencial válida, envío una solicitud desde el formulario web y
   aparece en Servicio Técnico en menos de 60 s, con origen='web' y
   firebase_id poblado.
3. El documento en Firestore queda en "sincronizada".
4. Corto la red: el indicador cambia, la app sigue operando, y al reconectar
   sincroniza sin duplicar.
5. El link de WhatsApp funciona con un número chileno sin +56.
6. Los tests pasan.
```

---

# FASE 4 — Empaquetado y entrega

```
FASE 4 — EMPAQUETADO Y ENTREGA

Leé primero docs/empaquetado-hallazgos.md (Fase 0.B) y partí de ahí.

--- BUILD
  - PyInstaller --onedir, con .spec versionado en el repo. No flags sueltos
    en un comando que después nadie recuerda.
  - El build final se hace EN WINDOWS. PyInstaller no hace cross-compilation.
  - Puntos de fallo a verificar en el EJECUTABLE, no en el código fuente:
      * firebase-admin / grpcio: el import más frágil del stack.
      * python-escpos con impresora USB necesita libusb-1.0.dll en Windows.
        Incluila o documentá su instalación.
      * openpyxl y las plantillas de Excel: rutas de recursos.
      * Iconos de qtawesome, assets/, imágenes de productos. Todo lo que hoy
        se resuelva con rutas relativas al script se rompe empaquetado. Usá
        sys._MEIPASS donde corresponda.
  - La base y la config ya viven en el directorio de datos (Fase 0), así que
    el ejecutable puede instalarse en Program Files. VERIFICALO instalando
    ahí de verdad.

--- CHECKLIST DE ENTREGA (generá docs/entrega.md)
  1. scripts/reset_db.py — base limpia, sin datos de prueba.
  2. Crear el usuario admin real. Verificar que no quede ninguno de prueba.
  3. Configuración del negocio: nombre, logo, nombres de las dos cajas,
     umbral de stock bajo.
  4. Cargar las categorías reales de cada línea.
  5. Configurar y probar la impresora térmica con "Imprimir prueba".
  6. Copiar serviceAccount.json al directorio de datos.
  7. Verificar que el respaldo diario se crea Y PROBAR UNA RESTAURACIÓN REAL:
     renombrá la base, restaurá desde un respaldo, confirmá que la app abre
     con los datos. Un respaldo que nunca se restauró no es un respaldo.
  8. Cargar inventario inicial por Excel.
  9. Prueba de humo: una venta en cada línea, un ciclo de servicio técnico de
     punta a punta, una solicitud desde el formulario web.

--- PRUEBA FINAL
En una máquina Windows LIMPIA, sin Python: la app arranca, se puede vender e
imprimir, el Dashboard muestra datos, la sincronización funciona, y al
reiniciar los datos siguen ahí con respaldo del día.
```

---

## Backlog post-entrega

No lo hagas antes de entregar. Anotado para que no se pierda:

- **Tabla `clientes`.** Los datos ya llegan de la web sin costo; normalizarlos
  es barato. Lo caro es capturar cliente en cada venta del POS: eso es
  fricción de mostrador y decisión de negocio, no técnica.
- **Embudo de conversión** solicitud → contactado → agendado → atendido.
  Necesita estados intermedios y marcas de tiempo por transición.
- **Agenda real** con citas, hora de inicio y duración. Única forma de
  calcular utilización. Es un módulo completo, no un campo.
- **Catálogo de tipos de servicio** con costo de repuestos, para que el margen
  de servicio técnico deje de ser cero.
- **Vista operativa en vivo** (variante 1b del MVP): feed de ventas, ventas
  por hora, turnos de caja.
- **Vista anual comparada** (variante 1c): reevaluar en 2027, cuando exista
  un año de historia.
- **Garantías**, egresos y flujo de caja, actualización remota, integración
  SII.
