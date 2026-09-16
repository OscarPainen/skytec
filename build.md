# Skytec — build & ejecución

Cliente: **Skytec** · Desarrollado por: **JobConsulting**.

## Ejecutar en desarrollo

```bash
pip install -r requirements.txt
python main.py
```

Al primer arranque se crea la base SQLite en el directorio de datos del
sistema (`%APPDATA%\Skytec\` en Windows, `~/Library/Application
Support/Skytec/` en macOS — ver `core/paths.py`), NO junto al ejecutable:
```
- Usuario admin inicial → **usuario:** `admin` · **clave:** `1234`
- Configuración base (nombre negocio, PoS "Tech"/"Fit", impresora, umbral stock bajo)
```

La ruta de la base se puede sobreescribir con la variable `SKYTEC_DB`; la
de la credencial de Firebase con `SKYTEC_FIREBASE_CREDENTIALS` (default:
`serviceAccount.json` en ese mismo directorio de datos — ver
`core/firebase_sync.py` y `.env.example`).

## Empaquetado (Fase 4)

```bash
pip install pyinstaller
pyinstaller skytec.spec
```

El `.spec` está versionado en la raíz del repo — no correr `pyinstaller`
con flags sueltos a mano, están todos documentados ahí. Detalle completo
de qué se probó y qué falta en `docs/empaquetado-hallazgos.md` y
`docs/entrega.md`.

**El build final se hace EN WINDOWS.** PyInstaller no hace
cross-compilation: lo que se arma en macOS/Linux sirve para probar que las
dependencias empaquetan bien (ya se hizo, ver los docs de arriba), pero no
es el ejecutable que se entrega.

## Puntos pendientes (del levantamiento)

- Vinculación PoS ↔ boletas SII (campo `ventas.boleta_sii` ya reservado, nullable).
- Alcance del catastro de inventario inicial.
- Confirmación de los dos nombres de PoS (por defecto: `Tech` / `Fit`, en `config`).
