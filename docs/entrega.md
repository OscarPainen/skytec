# Fase 4 — Checklist de entrega

2026-09-16 · Estado de cada punto: lo que ya se verificó desde acá (código,
sin Windows) vs. lo que es decisión/dato de Oscar vs. lo que solo se puede
probar en la máquina real de entrega.

Antes de arrancar esta lista: leer `docs/empaquetado-hallazgos.md` completo
(spike + build real), y **repetir el build en Windows** — ningún ítem de
acá reemplaza esa prueba.

---

## 1. `scripts/reset_db.py` — base limpia, sin datos de prueba

**Pendiente de correr para la entrega real.** El script existe, está
testeado (Fase 1) y ya se usó una vez en esta sesión para limpiar datos
viejos. Falta correrlo una última vez, después de las pruebas de humo del
ítem 9, para que la base que reciba el cliente no tenga nada de prueba.
Hace un respaldo automático antes de borrar — no hay riesgo de perder algo
sin querer.

## 2. Usuario admin real (sin ninguno de prueba)

**Pendiente, es decisión de Oscar.** Hoy el único usuario es `admin` con
clave `1234` (el default de `_seed_defaults` en `core/database.py`). Antes
de entregar: crear el usuario real (o cambiar la clave del admin) desde la
propia app, o decirme y agrego una función a `modules/ajustes` para
gestionar usuarios si no existe todavía un lugar para hacerlo — **no
existe hoy una pantalla para crear/editar usuarios**, solo el que sembró
`_seed_defaults`. Confirmar si hace falta antes de la entrega.

## 3. Configuración del negocio

**Pendiente, son datos reales de Oscar.** Nombre del negocio, logo, nombres
de las dos cajas (hoy en default "Tech"/"Fit"), umbral de stock bajo — todo
editable desde Ajustes, ya funciona. Falta que Oscar cargue los valores
reales.

## 4. Categorías reales de cada línea

**Pendiente, son datos reales de Oscar.** La tabla `categorias` y la
gestión desde Ajustes existen desde la Fase 1. Hoy tiene las 4 categorías
semilla (`Reparaciones`, `Accesorios`, `Celulares`, `Suplementos`) más lo
que se haya cargado de prueba — hay que revisarlas y dejar solo las reales.

## 5. Impresora térmica — configurar y probar

**Corregido un bloqueador real en esta sesión, pero sigue sin poder
probarse con hardware de verdad desde acá.** Se encontró y arregló que
imprimir por USB (la conexión por defecto) fallaba siempre por faltar
`pyusb` en `requirements.txt` — ver `docs/empaquetado-hallazgos.md`. Con
el paquete agregado, el error de "falta la librería USB" desaparece, pero
**nadie probó todavía imprimir en una impresora térmica real** — eso
necesita el hardware conectado, algo que no existe en esta sesión. Probar
con "Imprimir prueba" en Ajustes antes de dar esto por cerrado.

## 6. `serviceAccount.json` en el directorio de datos

**Hecho y verificado en producción real.** No es una tarea pendiente: ya
está en `~/Library/Application Support/Skytec/serviceAccount.json` con
permisos `600`, y la sincronización con Firestore real ya se probó de
punta a punta (ver memoria `firebase_sync_fase3`). En la máquina Windows
de entrega, este paso SÍ hay que repetirlo (copiar el archivo al
`%APPDATA%\Skytec\` de esa máquina).

## 7. Respaldo diario + restauración real

**Verificado de punta a punta, incluida la restauración.** No se había
probado nunca hasta esta sesión — el plan es explícito en que "un respaldo
que nunca se restauró no es un respaldo". Se probó: crear datos, generar
el respaldo, borrar la base (simulando el desastre), restaurar copiando el
archivo de respaldo, y confirmar que los datos vuelven exactos. Funcionó.

## 8. Inventario inicial por Excel

**Pendiente, son datos reales de Oscar.** La carga masiva (`modules/inventario/excel.py`)
está testeada desde la Fase 1, incluida la columna `linea_negocio`
obligatoria. Falta que Oscar cargue el catálogo real de productos.

## 9. Prueba de humo (una venta por línea + servicio técnico + solicitud web)

**Verificado por partes durante todo el proyecto, no como una sola corrida
continua en el ejecutable final.** Cada pieza se probó de verdad en algún
momento de las fases anteriores: venta directa (Fase 1), ciclo completo de
servicio técnico agendar→completar (Fase 1.5), solicitud real sincronizada
desde el formulario web (Fase 3, con datos de producción reales). Lo que
falta es correr las tres cosas seguidas, ya en el `.exe` instalado, como
control final antes de entregar — eso sí depende de tener el build de
Windows.

---

## Resumen para Oscar

De los 9 puntos: **2 ya están hechos y verificados de verdad** (6 y 7), **1
se corrigió en el camino pero falta probar con hardware real** (5), y **6
son datos/decisiones tuyas** que no me corresponde inventar (1, 2, 3, 4, 8,
9 — este último parcialmente, falta la corrida final en Windows).

## Prueba final (del plan, sin cambios)

En una máquina Windows limpia, sin Python instalado: la app arranca, se
puede vender e imprimir, el Dashboard muestra datos, la sincronización
funciona, y al reiniciar los datos siguen ahí con respaldo del día. Esto
es lo único que de verdad cierra la Fase 4 — todo lo de arriba es
preparación para llegar a este punto con confianza.
