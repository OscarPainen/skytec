# Fase 0.B — Hallazgos del spike de empaquetado

2026-09-16 · Experimento descartable, no integrado al proyecto (`spike/`,
gitignorado). Pregunta que respondía: ¿PySide6 + firebase-admin empaquetan
juntos con PyInstaller sin romperse?

## Resultado: SÍ funcionó, sin flags extra

`pyinstaller --onedir spike_app.py` a secas, ningún flag de los que el plan
tenía preparados como plan B (`--collect-all grpc`, `--collect-all
google.cloud`, `--hidden-import grpc._cython.cygrpc`, `--collect-data
certifi`, `.spec` a mano). Ninguno hizo falta.

Ejecuté el binario ya empaquetado (no el script suelto) con
`QT_QPA_PLATFORM=offscreen ./dist/spike_app/spike_app` y capturé la salida:

```
RESULTADO: firebase_admin OK — versión 7.5.0
```

Es decir: el import de `firebase_admin` funciona DENTRO del ejecutable
congelado, que es lo que había que probar — no alcanza con que funcione en
el intérprete suelto, PyInstaller puede fallar en encontrar módulos nativos
(`grpc._cython.cygrpc` es justamente uno de esos casos típicos) que sí
están disponibles fuera del empaquetado.

## Comando exacto usado

```
python3 -m venv venv_spike
venv_spike/bin/pip install PySide6 firebase-admin pyinstaller
venv_spike/bin/pyinstaller --onedir --noconfirm --name spike_app spike_app.py
```

Sin `.spec` escrito a mano — el que genera PyInstaller por defecto alcanzó.

## Tamaño del build

`dist/spike_app/` completo: **104 MB**. Es solo PySide6 + firebase-admin +
sus dependencias (grpc, google-cloud-firestore, cryptography, etc.) — el
build real de Skytec va a pesar más por sumar `openpyxl`, `python-escpos`
y el resto de la app, pero da una cota inferior realista.

## Advertencias (el build funcionó igual, pero quedan anotadas)

- **96 advertencias de PyInstaller** en `build/spike_app/warn-spike_app.txt`,
  todas del estilo "missing module named X — imported by Y (optional/delayed)"
  dentro de `google-auth`/`google-cloud`: rutas de autenticación alternativas
  que esta app no usa (`pyu2f` para llaves U2F físicas, `google.appengine`,
  fallback a `rsa`/`OpenSSL` puro). **Cero advertencias mencionando `grpc`
  directamente** — que era el riesgo puntual que señalaba el plan.
- `FutureWarning` de `google-auth`: Python 3.9 está en fin de vida, las
  próximas versiones de `google-auth`/`google-cloud-*` van a dejar de
  soportarlo. No bloquea nada hoy; si en algún momento se sube la versión de
  Python del proyecto, revisar que siga compilando.
- `NotOpenSSLWarning` de `urllib3`: viene de que macOS trae LibreSSL, no
  OpenSSL. Es una advertencia específica de este macOS de desarrollo — en
  Windows probablemente no aparezca (Windows no usa LibreSSL), pero **eso
  no se verificó**, ver la sección de Windows abajo.

## Versiones exactas usadas en el spike

| Paquete | Versión |
|---|---|
| Python | 3.9.6 |
| PySide6 | 6.10.3 |
| firebase-admin | 7.5.0 |
| grpcio | 1.80.0 |
| PyInstaller | 6.22.3 |

## ⚠️ Falta repetir esto en Windows

Este spike corrió en **macOS (arm64)**. PyInstaller no hace
cross-compilation: un build hecho en macOS empaqueta para macOS, nunca para
Windows. Que haya funcionado acá **reduce el riesgo pero no lo elimina** —
antes de la Fase 4 real hay que repetir exactamente este mismo experimento
en una máquina Windows limpia (los mismos 3 comandos de arriba) y confirmar
que el import funciona ahí también. Los candidatos más probables a fallar
distinto en Windows son justamente los que no se pudieron probar acá:
`grpcio` (tiene binarios nativos por plataforma) y `python-escpos` con la
impresora USB (necesita `libusb-1.0.dll`, ver Fase 4 del plan).

## Conclusión para la Fase 4

Semáforo verde para seguir: no hace falta un `.spec` custom ni flags
especiales solo por tener `firebase-admin` en el proyecto. El build real
puede armarse con `--onedir` simple como punto de partida, ajustando desde
ahí si aparece algo nuevo al sumar el resto de las dependencias — pero
repitiendo la prueba en Windows antes de confiar en el resultado de acá.

---

# Fase 4 — Empaquetado de la app real (no el spike aislado)

2026-09-16 · Mismo macOS, mismo `--onedir`, pero ahora con `main.py` de
verdad y todas las dependencias de `requirements.txt`. El `.spec` resultante
quedó versionado en `skytec.spec` (raíz del repo).

## Resultado: arranca bien, con un bug real encontrado y corregido

Ejecuté el binario empaquetado (`./dist/skytec/Skytec`, offscreen) con una
base de datos de prueba aislada y confirmé:
- Se crea la base SQLite con `journal_mode=wal` (Fase 0 funcionando dentro
  del ejecutable, no solo en desarrollo).
- Se crea el directorio de respaldos.
- Llega al login sin ninguna excepción ni módulo faltante.
- Los íconos de `qtawesome` se renderizan de verdad dentro del ejecutable
  (lo probé con un script aparte que arma un `QIcon` y verifica que el
  pixmap no salga vacío — no alcanza con que la app no crashee, un ícono
  vacío no crashea tampoco). Sin flags extra: el hook de
  `pyinstaller-hooks-contrib` lo resuelve solo.

**Bug real encontrado (no en el spike, en la app real): imprimir por USB
—la conexión por defecto en Ajustes— fallaba siempre.** `python-escpos`
necesita el paquete `pyusb` para su backend USB, y no estaba en
`requirements.txt`. Sin él, `escpos.printer.Usb(...)` no lanza error al
crearse, pero cualquier intento de imprimir termina en
`RuntimeError: Printing with USB connection requires a usb library...`.
La app no crashea (`core/printing.py` ya envolvía esto en `PrintingError`
con mensaje humano, como corresponde), pero imprimir simplemente no
funcionaba. **Corregido:** se agregó `pyusb>=1.2` a `requirements.txt` y se
instaló en el entorno real (`skytec`, conda) y en el de build; confirmado
que el `RuntimeError` desaparece.

## Dos arreglos de código previos a este build (rutas relativas)

Antes de empaquetar la app real se corrigieron dos lugares que asumían
"vivo junto al script" — el mismo tipo de bug que ya se había resuelto para
la base de datos en la Fase 0, pero que seguía sin corregirse acá:
- `ui/styles.py` — el PNG cacheado del ícono del combo se guardaba en
  `<raíz del proyecto>/assets/_cache`. En un ejecutable instalado en
  Program Files, esa carpeta no tiene permiso de escritura. Ahora usa
  `core.paths.app_data_dir() / "cache"`.
- `modules/inventario/page.py` — las fotos de producto se guardaban en
  `<raíz del proyecto>/assets/productos`, mismo problema. Ahora usan
  `app_data_dir() / "assets" / "productos"`.

No hubo que migrar nada: no existían fotos de producto reales todavía.

## Otras advertencias del build real (no bloquean nada)

- `escpos.printer.win32raw` pide `win32print`/`pywintypes` (paquete
  `pywin32`) — solo hace falta si algún día se usa esa vía de impresión en
  Windows. No es la que usa esta app (usa `Usb`/`Network`/`Serial`).
- `escpos.printer.serial` pide `serial` (paquete `pyserial`) — falta si se
  usa la opción "Serial" de Ajustes. Hoy no está en `requirements.txt` a
  propósito: no se agregó sin preguntar, ya que no es la conexión por
  defecto. **Si Oscar usa o va a usar una impresora por puerto serial,
  avisar para agregar `pyserial`.**
- `escpos.printer.cups` pide `cups` — no se usa en Windows, ignorar.

## Tamaño del build real

`dist/skytec/` completo: **156 MB** (vs. 104 MB del spike aislado — la
diferencia son `openpyxl`, `python-escpos`+`pyusb`, y el resto de módulos
propios de la app).

## Decisión pendiente, no bloqueante: consola visible o no

`skytec.spec` quedó con `console=True` a propósito: la app no tiene
logging propio, solo `print()` (p. ej. "Migrado skytec.db legado...",
"Advertencia: journal_mode..."). Con `console=False` esos avisos
desaparecen sin dejar rastro en ningún lado — útil para diagnosticar algo
en el local, pero se ve una ventana de consola negra al abrir la app.
Queda anotado en el propio `.spec` para que Oscar decida cuándo prefiera
la versión "prolija" sin consola.

---

# Fase 4 — Cambio de conexión por defecto de la impresora: "Windows" en vez de "USB"

2026-09-17 · Motivado por una prueba real en la Mac de desarrollo: al
probar la impresión, `core/printing.py` devolvió "backend no disponible"
(`usb.core.NoBackendError`, mensaje de pyusb). La causa no era un bug de
Skytec — a esta Mac le faltaba la librería nativa `libusb` (Homebrew:
`brew install libusb`; el paquete Python `pyusb` es solo el wrapper). Una
vez instalada, imprimir por USB funcionó contra una impresora real
conectada.

Pero esto expuso el problema real para la máquina Windows del local:
**pyusb necesita, además de `libusb-1.0.dll`, que el driver de la
impresora esté reemplazado por WinUSB o libusbK** (típicamente con una
herramienta como Zadig) — Windows ata las impresoras USB a su propio
driver (`usbprint`) por defecto, y libusb no puede tomar un dispositivo
que ya tiene otro driver de kernel encima. Es un paso manual, por máquina,
que no se puede automatizar desde la app ni el instalador.

**Cambio: la conexión por defecto ahora es "Windows"**, no "USB". Usa
`escpos.printer.Win32Raw` (vía `pywin32`), que manda los bytes ESC/POS a
través del driver que Windows ya instaló para la impresora — el mismo que
usa cualquier programa que "imprime" normalmente. Sin Zadig, sin
reemplazar drivers, sin `libusb-1.0.dll`. Es el camino de menor fricción
para "llegar e importar" en la máquina real.

Cambios:
- `requirements.txt`: `pywin32>=306; sys_platform == "win32"` (marcador de
  entorno — no intenta instalarse en macOS/Linux, donde fallaría).
- `core/database.py` (`DEFAULT_CONFIG`): `impresora_conexion` default pasa
  de `"usb"` a `"windows"`; nueva clave `impresora_windows_nombre` (vacía =
  usa la impresora predeterminada del sistema).
- `core/printing.py`: nueva rama `conexion == "windows"` en
  `_abrir_impresora()`, y `impresoras_windows()` para listar las
  impresoras instaladas (usado por Ajustes; devuelve `[]` fuera de
  Windows, nunca lanza).
- `modules/ajustes/page.py`: nueva opción "Windows (recomendado)" primera
  en el combo de Conexión, con un selector (editable) de la impresora de
  Windows a usar.
- "USB" sigue disponible como opción en Ajustes, para impresoras sin
  driver de Windows instalado, o para seguir probando en esta Mac de
  desarrollo (donde "Windows" no puede funcionar: no existe `pywin32` en
  macOS, y aunque existiera, `win32print` es una API exclusiva de Windows).

**No probado contra Windows real todavía** (no hay máquina Windows desde
acá) — el riesgo que queda es si el driver que Windows instala solo para
verla en "Dispositivos e impresoras" acepta bytes ESC/POS crudos vía
`Win32Raw`/`win32print.WritePrinter` sin transformarlos. Para la inmensa
mayoría de impresoras térmicas de recibos (que se instalan con un driver
"genérico / de texto" o el propio del fabricante en modo RAW) esto
funciona de fábrica; impresoras que solo traen driver GDI (pensado para
imprimir páginas, no texto crudo) son la excepción y necesitarían volver a
la opción "USB" con el reemplazo de driver de más arriba.

## ⚠️ Sigue pendiente Windows (no cambia respecto de la sección de arriba)

Todo lo de esta sección también corrió en macOS (arm64). El build real
agrega un candidato más a la lista de "probar en Windows antes de
confiar": `pyusb` + `libusb-1.0.dll` — confirmar que el import funciona Y
que se puede efectivamente hablar con una impresora USB conectada de
verdad, algo que no se puede probar desde acá.
