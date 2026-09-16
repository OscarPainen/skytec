# -*- mode: python ; coding: utf-8 -*-
#
# Fase 4 — spec versionado del build de producción. Generado a partir del
# --onedir por defecto de PyInstaller y verificado de verdad en macOS
# (ver docs/empaquetado-hallazgos.md): la app arranca, migra la base, crea
# respaldos, y los íconos de qtawesome se renderizan sin flags extra.
#
# PENDIENTE, no verificado desde acá (PyInstaller no hace cross-compilation):
# correr este mismo .spec EN WINDOWS antes de confiar en el resultado.
#
# Uso: pyinstaller skytec.spec   (desde la raíz del proyecto)

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Skytec',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    # console=True a propósito por ahora: la app no tiene logging propio,
    # solo print() (ver "Advertencia: journal_mode..." en core/database.py,
    # por ejemplo). Con console=False esos avisos desaparecen sin dejar
    # rastro en ningún lado. Cambiar a False una vez que el negocio lleve
    # un tiempo estable y ya no haga falta ver esa salida — es una decisión
    # de Oscar, no algo que haya que resolver antes de la entrega.
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon=['assets/skytec.ico'],  # no existe todavía un ícono propio;
    # agregarlo acá cuando Oscar tenga uno (formato .ico para Windows).
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Skytec',
)
