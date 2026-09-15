# Fase 1.5 — Auditoría del flujo Servicio Técnico → Agenda → Venta

2026-09-15 · Diagnóstico solamente, nada de esto está implementado. Todo lo
marcado como "confirmado" se probó con código real corriendo contra una base
temporal (no se dedujo leyendo nomás) — los scripts de prueba no quedaron en
el repo, corrieron y se descartaron.

---

## 1. Diagrama del flujo completo

```
SOLICITUD (web o manual)
  │
  │  crear_solicitud_manual()                    escribe: solicitudes_reparacion
  │  estado='pendiente'                                   (fila nueva)
  ▼
[Servicio Técnico] bandeja "Pedidos" (pendiente/revisada)
  │
  │  guardar_servicio(fecha, precio, detalles)    escribe: servicios_tecnicos (upsert)
  │  estado 'pendiente' -> 'revisada'                      solicitudes_reparacion.estado
  ▼
"Cliente aceptó"  (botón en SolicitudDialog)
  │
  │  aceptar(solicitud_id)
  │    1. exige precio > 0 y que no tenga venta_id ya
  │    2. pos.registrar_venta(...)                escribe: ventas (fila nueva)
  │       tipo='servicio_tecnico'                          venta_items (fila nueva)
  │       linea_negocio='reparacion', costo=0              movimientos_stock: NO
  │                                                         (el ítem no tiene
  │                                                         producto_id, no hay
  │                                                         stock que mover)
  │    3. UPDATE servicios_tecnicos                escribe: servicios_tecnicos.venta_id
  │       venta_id=?, estado='aceptada'                     servicios_tecnicos.estado
  │    4. UPDATE solicitudes_reparacion             escribe: solicitudes_reparacion.estado
  │       estado='aceptada'                                 = 'aceptada'
  │
  │  señal SolicitudDialog.aceptada -> MainWindow salta a pestaña Agenda
  ▼
[Agenda] vista "Agendados" = últimos 15 (por fecha de creación de la
         SOLICITUD, no del cambio de estado) con estado en
         (aceptada, en_reparacion, completada, no_retirada)
  │
  │  botones "En reparación" / "Completada" / "No retirada"
  │  cambiar_estado(solicitud_id, estado)          escribe: SOLO
  │                                                         solicitudes_reparacion.estado
  │                                                 (servicios_tecnicos.estado
  │                                                 queda pegado en 'aceptada'
  │                                                 para siempre — ver hallazgo 4)
  │
  │  "Ver nota de venta" (SOLO visible si se abrió desde Agenda)
  ▼
NotaVentaDialog -> botón "Imprimir" (PrintWorker, ESC/POS)
```

**El ingreso (`ventas` + `venta_items`) se registra en el paso "Cliente
aceptó" — antes de hacer el trabajo, antes de que el cliente retire y
pague.** Ningún paso posterior (en_reparacion, completada, no_retirada,
eliminar) modifica esa venta ni el total. Esto responde las preguntas 1 y 2
de una.

---

## 2. Respuestas puntuales

**P3 — ¿Se revierte la venta si el equipo queda `no_retirada`?**
Confirmado que NO. Prueba: acepté una solicitud (crea venta con total
$50.000), la marqué `no_retirada`, y la venta sigue en la base con el mismo
total. `cambiar_estado()` solo hace `UPDATE solicitudes_reparacion SET
estado=?` — no toca `ventas` ni `venta_items` ni `movimientos_stock` en
ningún caso. Tampoco `eliminar()`: borra la solicitud y el servicio, pero el
docstring dice explícitamente "la nota de venta (si existe) se conserva" —
y así es, verificado.

**P4 — ¿Se puede aceptar dos veces y generar dos ventas?**
Confirmado que NO — probado de verdad, no asumido. `aceptar()` lee
`s.get("venta_id")` antes de vender y lanza `ValueError` si ya existe. Doble
llamada real a `aceptar()` sobre la misma solicitud: la segunda falla con
"Este servicio ya fue aceptado y tiene nota de venta." y no se crea una
segunda fila en `ventas`.

**P5 — ¿Dónde quedó la nota de venta?**
El botón "Ver nota de venta" en `SolicitudDialog` solo aparece cuando el
diálogo se abrió con `mostrar_nota=True`, y ESO SOLO pasa desde
`AgendaPage._abrir_fila()` (modules/agenda/page.py:122). Desde
`ServicioTecnicoPage._abrir_fila()` (modules/servicio_tecnico/page.py:136) el
diálogo se abre con `mostrar_nota=False` siempre — incluido cuando filtrás
por "Todas las solicitudes" o "Aceptada / agendada" y abrís una solicitud
YA aceptada. Ahí el botón "Cliente aceptó" está deshabilitado (ya tiene
venta) y no hay ningún otro botón que lleve a la nota. **Sí existe un
camino para ver/imprimir la nota (vía Agenda), pero solo uno — si la
encontrás por Servicio Técnico > Todas, no hay forma de llegar a ella desde
ahí.**

**P6 — `servicios_tecnicos.estado` vs `solicitudes_reparacion.estado`:
¿cuál manda?**
Manda `solicitudes_reparacion.estado` — es el único que se lee en cualquier
parte de la UI (`_SELECT` en repo.py ni siquiera trae `t.estado` en el
`SELECT`, solo `s.*`). `servicios_tecnicos.estado` se escribe UNA vez
(`aceptar()`, se fija en `'aceptada'`) y nunca más se toca ni se lee en
ningún archivo del proyecto — confirmado con grep, cero coincidencias fuera
de esa única escritura. Es una columna viva en el esquema pero muerta en el
código: no se desincroniza "por error", queda deliberadamente congelada
porque nadie la usa.

**P7 — `'vencida'` nunca se escribe: ¿algo la busca en la base y falla?**
No. Confirmado por grep: ningún `WHERE estado = 'vencida'` existe contra la
base — `vencido` se calcula siempre en Python (`repo._fila`). El único lugar
donde aparece el string `'vencida'` fuera del `CHECK` es la etiqueta de UI
(`ESTADOS["vencida"] = "Vencida"`), que queda de adorno sin causar ningún
fallo.

**P8 — Agenda "últimos 15": ¿es un corte real y qué se pierde?**
Confirmado con prueba forzada (fechas de creación controladas): con 16
solicitudes aceptadas, la más vieja **desaparece** de `agenda_agendados(15)`
— aunque su estado sea `en_reparacion` (trabajo activo, sin terminar). No
aparece en `vencidos()` (solo mira `fecha_entrega_solicitada`, no
"cuántas hay adelante en la cola"), ni en `no_retiradas()`, ni en
`pedidos()`. **Queda invisible en toda la UI**, aunque sigue en la base y
sigue con estado activo.

---

## 3. Hallazgos, ordenados por impacto

### 1. (CRÍTICO) El ingreso se reconoce al aceptar, no al completar/cobrar — RESUELTO (2026-09-15)
Una reparación aceptada y nunca retirada queda contada como venta para
siempre. Con volumen real esto infla los ingresos reportados por cualquier
cosa que sume `ventas.total` (incluido el futuro Dashboard) con trabajos que
nunca se cobraron.
**Recomendación:** mover el registro de la venta de "Cliente aceptó" a
"Completada" (o agregar un estado explícito de cobro). Trade-off: hoy
`aceptar()` es lo que genera el `venta_id` que identifica al servicio en
Agenda y habilita "Ver nota de venta" — si el ingreso se reconoce después,
hay que decidir con qué se identifica/agenda un servicio ANTES de que exista
la venta (probablemente: agendar por `solicitud_id`, crear la venta recién
al completar). Es un cambio de forma, no cosmético.

**Implementado:** `aceptar()` ya no llama a `pos.registrar_venta()` — solo
agenda (valida precio guardado, exige que la solicitud siga siendo un
"pedido"). La venta se genera en `completar()` (nueva función), disparada
únicamente al marcar "Completada" desde `SolicitudDialog._estado()` —los
otros dos botones de transición (`en_reparacion`, `no_retirada`) siguen
siendo cambios de estado puros, sin tocar `ventas`. El guardrail contra
doble cobro se movió de "¿ya tiene venta_id?" (en `aceptar`) a lo mismo pero
en `completar`; el guardrail contra doble aceptación pasó a mirar el estado
de la solicitud en vez de `venta_id` (que ahora no existe en ese punto).
Cubierto en `tests/test_servicio_tecnico_repo.py`, incluido el caso central:
agendar y marcar `no_retirada` sin completar nunca deja `ventas` en 0 filas
para esa solicitud. Identificación de un servicio agendado en Agenda sigue
siendo por `solicitud_id` (nunca dependió de `venta_id`), así que no hizo
falta ningún cambio ahí — la preocupación del trade-off de arriba no aplicó
en la práctica.

**Fuera de alcance de este fix, a propósito:** si un servicio ya
`completada` (con venta y cobro ya hechos) se marca después como
`no_retirada`, la venta NO se revierte. Es un escenario distinto (plata que
sí entró, equipo que después no se retira) y decidí no inventar una lógica
de reversión/anulación sin que Oscar la pida — eso sería un cambio de
producto, no la corrección de este bug.

### 2. (ALTO) Un trabajo activo puede desaparecer de la Agenda sin avisar — RESUELTO (2026-09-15)
Confirmado con prueba: pasa hoy mismo con 16+ solicitudes aceptadas
históricamente, no hace falta llegar a un volumen enorme. El corte es por
"últimos N creados", no por "estados que siguen abiertos".
**Recomendación:** separar el corte por estado — los estados NO terminales
(`aceptada`, `en_reparacion`) no deberían tener límite (son la cola de
trabajo real, tiene que verse completa); el límite de 15 tiene sentido para
`completada`/`no_retirada` como historial reciente. Trade-off: dos consultas
en vez de una, un poco más de código en `agenda_agendados()`, pero es
chico comparado con el riesgo de perder de vista un trabajo real.

**Implementado:** `agenda_agendados()` recorre `listar()` una sola vez
(sigue viniendo ordenado por más reciente) y arma el resultado con una
regla distinta por grupo: todo lo que esté en `aceptada`/`en_reparacion` se
conserva siempre; de `completada`/`no_retirada` solo se conservan los
`limite` más recientes. No hizo falta una segunda consulta — el trade-off
de "dos consultas" que anticipé no se dio, un solo recorrido alcanza.
Cubierto en `tests/test_servicio_tecnico_repo.py::test_agenda_agendados_nunca_recorta_un_activo`,
reproduciendo el mismo escenario que probé a mano acá arriba (16 servicios,
uno activo y viejo, 15 terminados y más nuevos): el activo sigue visible,
los terminados se recortan a 15.

### 3. (MEDIO) La nota de venta no es alcanzable desde todos los caminos — RESUELTO (2026-09-15)
Si encontrás una solicitud ya aceptada filtrando por "Todas las solicitudes"
en Servicio Técnico (no por Agenda), no hay botón para ver/reimprimir su
nota.
**Recomendación:** la forma más simple es sacar el gate de `mostrar_nota` y
mostrar "Ver nota de venta" siempre que `self.s.get("venta_id")` exista, sin
importar desde dónde se abrió el diálogo. Trade-off: ninguno real que yo vea
— el comentario en el código sugiere que se ocultó a propósito para que
"Servicio Técnico se quede solo con las solicitudes", pero eso es una
preferencia de organización de pantallas, no una razón funcional para
esconder una acción que el usuario podría necesitar.

**Implementado:** saqué el parámetro `mostrar_nota` de `SolicitudDialog`
(ya no cumplía ninguna función más que ocultar el botón) y el botón "Ver
nota de venta" ahora aparece siempre que `self.s.get("venta_id")` exista,
sin importar si el diálogo se abrió desde Servicio Técnico o desde Agenda.
Cambio acotado a `modules/servicio_tecnico/page.py` y
`modules/agenda/page.py` (un `kwarg` menos en la llamada); no toqué
`repo.py` ni la base — no hacía falta test de pytest nuevo, no hay lógica
de datos involucrada.

### 4. (BAJO, cosmético) `servicios_tecnicos.estado` es una columna muerta — DOCUMENTADO (2026-09-15)
Se escribe una vez y no se lee nunca. No causa ningún bug hoy, pero confunde
a cualquiera que lea el esquema pensando que refleja el estado real (que
vive en `solicitudes_reparacion.estado`).
**Recomendación:** en la migración v4 ya agregamos columnas; se podría
aprovechar una futura migración para eliminar `servicios_tecnicos.estado`
directamente, o dejarla y agregar un comentario en el esquema explicando que
es vestigial. No urge — es limpieza, no corrección de un bug.

**Implementado (la opción chica, a propósito):** NO agregué una migración
para eliminar la columna — es la opción de mayor riesgo para el beneficio
más chico de las dos, y el hallazgo es "bajo, cosmético". Además, tocar el
string de la migración v1 para comentar ahí mismo hubiera violado la regla
del CLAUDE.md de nunca editar una migración ya aplicada. En cambio, dejé el
comentario justo donde se escribe la columna (`modules/servicio_tecnico/repo.py`,
en `aceptar()` y `completar()`), que es donde a futuro alguien se va a hacer
la pregunta "¿por qué escribo esto si nadie lo lee?". Comportamiento sin
cambios — cero riesgo, solo se resolvió la confusión.

---

## 4. Qué decidir antes de seguir

No implementé nada de esto. Los 4 hallazgos están ordenados por impacto en
los números que va a mostrar el Dashboard (Fase 2). El hallazgo 1 es el que
más importa: si no se resuelve (o se decide conscientemente dejarlo así por
ahora), el Dashboard va a reportar ingresos que no son caja real. Los
hallazgos 2 y 3 son bugs de UX/operación, no de datos — no afectan al
Dashboard pero sí a cómo se usa la Agenda día a día.
