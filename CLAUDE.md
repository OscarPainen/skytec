# Contexto del proyecto Skytec

App de escritorio en Python (PySide6) para POS/ERP de un negocio que repara 
celulares, vende tecnología y suplementos. Cliente: HOB Consulting (Oscar).

## Estado actual
- Entorno local funcionando (venv activo, main.py corre bien)
- Login: admin / 1234
- Firebase: Oscar ya envió las credenciales (.env con prefijo VITE_, o sea 
  SDK cliente, no cuenta de servicio). Falta confirmar con Oscar si su rama 
  ya tiene la lógica de conexión implementada, para no duplicar trabajo.
- Quick wins de estilo (contraste de textos/botones) YA RESUELTOS: texto 
  "Sin conexión" ilegible, rojo hardcodeado en servicio técnico, botón 
  "Entrar" del login sin estilo estándar.

## Trabajando en ahora
- Category tags: marcar cada venta como reparación/tecnología/suplemento
  (esto alimenta directamente al Dashboard, es prioridad antes que Ajustes)

## Pendiente después de category tags
- Pestaña de Ajustes: categorías, umbral de stock, tipo de conexión impresora

## Prioridad general del proyecto (en orden)
1. Quick wins (casi listo — falta category tags y Ajustes)
2. Dashboard de las 3 líneas de negocio (LA prioridad para Oscar)
3. Nota de venta + garantía, lógica de agenda
4. Actualización remota + impresora térmica (NO comprometer antes de vacaciones, 9 sept)

## Reglas de trabajo
- Yo soy junior en Python — explica el porqué de los cambios, no solo el qué
- No apliques cambios grandes sin mostrarme el diagnóstico primero
- No escribas código de conexión a Firebase todavía (falta confirmar con Oscar 
  qué enfoque usa su rama)