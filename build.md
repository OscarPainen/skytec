# Skytec — build & ejecución

Cliente: **Skytec** · Desarrollado por: **JobConsulting**.

## Ejecutar en desarrollo

```bash
pip install -r requirements.txt
python main.py
```

Al primer arranque se crea `skytec.db` (SQLite, local) con:
- Usuario admin inicial → **usuario:** `admin` · **clave:** `1234`
- Configuración base (nombre negocio, PoS "Tech"/"Fit", impresora, umbral stock bajo)

La ruta de la base se puede sobreescribir con la variable `SKYTEC_DB`.

## Empaquetado (Fase 7 — pendiente)

PyInstaller `--onedir` + Inno Setup. Se documentará al llegar a esa fase.

## Puntos pendientes (del levantamiento)

- Vinculación PoS ↔ boletas SII (campo `ventas.boleta_sii` ya reservado, nullable).
- Alcance del catastro de inventario inicial.
- Confirmación de los dos nombres de PoS (por defecto: `Tech` / `Fit`, en `config`).
