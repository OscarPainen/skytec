"""Acceso a datos del Dashboard: todo lee de v_operaciones (core/database.py,
migración v5), la vista que unifica venta_items+ventas en una fila por ítem
vendido. No hay SQL directo sobre venta_items/ventas acá — si el Dashboard
necesita un dato nuevo, se agrega a la vista, no se reinventa el join.

Robustez no negociable (ver docs/plan-ejecucion.md, Fase 2):
  - división por cero -> 0, nunca None ni excepción.
  - un período sin datos devuelve la estructura completa en ceros.
  - las 3 líneas de negocio aparecen siempre en por_linea_negocio.
"""
from __future__ import annotations

from datetime import date, timedelta

from core import database

LINEAS_NEGOCIO = ("reparacion", "tecnologia", "suplemento")


# ── Rangos de fecha (lógica pura, sin SQL) ──────────────────────────────────
def rango_periodo(tipo: str, hoy: date | None = None) -> tuple[str, str]:
    """(desde, hasta) inclusive, 'YYYY-MM-DD'. hoy es inyectable para tests.

    'semana' = lunes de esta semana -> hoy. 'mes' = 1° del mes -> hoy.
    'año' = 1° de enero -> hoy. 'todo' = desde siempre -> hoy. Todos "a la
    fecha" (no cierran el período), porque el Dashboard se mira en cualquier
    momento del período en curso, no solo al final.
    """
    hoy = hoy or date.today()
    if tipo == "semana":
        inicio = hoy - timedelta(days=hoy.weekday())
    elif tipo == "mes":
        inicio = hoy.replace(day=1)
    elif tipo == "año":
        inicio = hoy.replace(month=1, day=1)
    elif tipo == "todo":
        inicio = date(1, 1, 1)
    else:
        raise ValueError(f"Tipo de período inválido: {tipo}")
    return inicio.isoformat(), hoy.isoformat()


def rango_periodo_anterior(tipo: str, desde: str, hasta: str) -> tuple[str, str] | None:
    """El período equivalente inmediatamente anterior, misma cantidad de
    días. None para 'todo' (no hay "anterior a desde siempre").

    Por días (no por mes/año calendario) a propósito: si hoy es 15 de
    septiembre, "mes" da un período de 15 días (1 al 15) — comparar contra
    agosto completo (31 días) sería injusto. Contra el 1-15 de agosto sí es
    una comparación pareja, y esto lo da gratis para cualquier tipo."""
    if tipo == "todo":
        return None
    d = date.fromisoformat(desde)
    h = date.fromisoformat(hasta)
    dias = (h - d).days + 1
    fin_anterior = d - timedelta(days=1)
    inicio_anterior = fin_anterior - timedelta(days=dias - 1)
    return inicio_anterior.isoformat(), fin_anterior.isoformat()


def variacion_pct(actual: float, anterior: float) -> float | None:
    """% de variación de actual vs anterior. None si anterior es 0 (no hay
    base para comparar — mostrar "0% de variación" sería mentir)."""
    if not anterior:
        return None
    return round((actual - anterior) / anterior * 100, 1)


# ── Agregaciones ─────────────────────────────────────────────────────────────
def resumen_periodo(desde: str, hasta: str) -> dict:
    """Los 4 KPIs totales del período: ventas, margen, n_ventas (nº de
    tickets, no de ítems), ticket_promedio. Todo en 0 si no hay datos.

    margen_pct es None (no un número) cuando HAY ventas pero el costo total
    es 0 — no es que el margen sea 100%, es que no hay costos cargados para
    calcularlo. Mostrar "100%" ahí sería un dato faltante disfrazado de
    buena noticia (rediseño Fase 2.5, Problema 2). Con ventas=0 (período
    vacío, nada que calcular) sigue siendo 0, no None — son estados
    distintos: "sin datos" vs "hay datos pero falta un insumo"."""
    conn = database.get_connection()
    try:
        row = conn.execute(
            "SELECT COALESCE(SUM(monto),0) AS ventas, COALESCE(SUM(margen),0) AS margen, "
            "COALESCE(SUM(costo),0) AS costo, COUNT(DISTINCT venta_id) AS n_ventas "
            "FROM v_operaciones WHERE dia BETWEEN ? AND ?",
            (desde, hasta),
        ).fetchone()
    finally:
        conn.close()
    ventas, margen, costo, n_ventas = row["ventas"], row["margen"], row["costo"], row["n_ventas"]
    if not ventas:
        margen_pct = 0
    elif not costo:
        margen_pct = None
    else:
        margen_pct = round(margen / ventas * 100, 1)
    return {
        "ventas": ventas,
        "margen": margen,
        "costo": costo,
        "margen_pct": margen_pct,
        "n_ventas": n_ventas,
        "ticket_promedio": round(ventas / n_ventas) if n_ventas else 0,
    }


def por_linea_negocio(desde: str, hasta: str) -> list[dict]:
    """Una fila por línea, SIEMPRE las 3, en el orden LINEAS_NEGOCIO — un
    cero es información (esa línea no vendió nada), una fila ausente sería
    un bug visual. n_items es la cantidad de ítems vendidos en esa línea
    (no de ventas: una venta puede tener ítems de más de una línea)."""
    conn = database.get_connection()
    try:
        filas = conn.execute(
            "SELECT linea_negocio, COALESCE(SUM(monto),0) AS ventas, "
            "COALESCE(SUM(margen),0) AS margen, COUNT(*) AS n_items "
            "FROM v_operaciones WHERE dia BETWEEN ? AND ? GROUP BY linea_negocio",
            (desde, hasta),
        ).fetchall()
    finally:
        conn.close()
    por_linea = {r["linea_negocio"]: dict(r) for r in filas}
    total_ventas = sum(v["ventas"] for v in por_linea.values())
    resultado = []
    for linea in LINEAS_NEGOCIO:
        d = por_linea.get(linea, {"ventas": 0, "margen": 0, "n_items": 0})
        resultado.append({
            "linea_negocio": linea,
            "ventas": d["ventas"],
            "margen": d["margen"],
            "n_items": d["n_items"],
            "participacion_pct": round(d["ventas"] / total_ventas * 100, 1) if total_ventas else 0,
        })
    return resultado


def por_categoria(linea: str, desde: str, hasta: str) -> list[dict]:
    """Desglose de una línea por categoría, ordenado de mayor a menor venta."""
    conn = database.get_connection()
    try:
        filas = conn.execute(
            "SELECT categoria, COALESCE(SUM(monto),0) AS ventas, COUNT(*) AS n_items "
            "FROM v_operaciones WHERE dia BETWEEN ? AND ? AND linea_negocio = ? "
            "GROUP BY categoria ORDER BY ventas DESC",
            (desde, hasta, linea),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in filas]


def por_caja(desde: str, hasta: str) -> list[dict]:
    """Corte por caja (ventas.pos_origen). Ignora ítems sin caja asignada
    (servicio técnico: pos_origen='Servicio Técnico' si viene así, o NULL si
    no se seteó — un NULL no es una caja real, no tiene sentido en la tabla)."""
    conn = database.get_connection()
    try:
        filas = conn.execute(
            "SELECT caja, COALESCE(SUM(monto),0) AS ventas, COUNT(DISTINCT venta_id) AS n_ventas "
            "FROM v_operaciones WHERE dia BETWEEN ? AND ? AND caja IS NOT NULL "
            "GROUP BY caja ORDER BY ventas DESC",
            (desde, hasta),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in filas]


MESES_CORTOS = ("Ene", "Feb", "Mar", "Abr", "May", "Jun",
                 "Jul", "Ago", "Sep", "Oct", "Nov", "Dic")


def serie_temporal(desde: str, hasta: str, granularidad: str) -> list[dict]:
    """[{clave, etiqueta, ventas, n_ventas}] — TODOS los períodos del rango,
    incluidos los que valen 0 (un día sin ventas es un dato, no una
    ausencia: si se salteara, el gráfico de barras mentiría por omisión).

    granularidad: 'dia' (una barra por día — usado en Semana y Mes) o 'mes'
    (una barra por mes — usado en Año)."""
    if granularidad not in ("dia", "mes"):
        raise ValueError(f"granularidad inválida: {granularidad}")
    columna = "dia" if granularidad == "dia" else "periodo"
    conn = database.get_connection()
    try:
        filas = conn.execute(
            f"SELECT {columna} AS clave, COALESCE(SUM(monto),0) AS ventas, "
            "COUNT(DISTINCT venta_id) AS n_ventas FROM v_operaciones "
            f"WHERE dia BETWEEN ? AND ? GROUP BY {columna}",
            (desde, hasta),
        ).fetchall()
    finally:
        conn.close()
    por_clave = {r["clave"]: {"ventas": r["ventas"], "n_ventas": r["n_ventas"]} for r in filas}

    resultado: list[dict] = []
    if granularidad == "dia":
        actual = date.fromisoformat(desde)
        fin = date.fromisoformat(hasta)
        while actual <= fin:
            clave = actual.isoformat()
            datos = por_clave.get(clave, {"ventas": 0, "n_ventas": 0})
            resultado.append({"clave": clave, "etiqueta": str(actual.day), **datos})
            actual += timedelta(days=1)
    else:
        actual = date.fromisoformat(desde).replace(day=1)
        fin = date.fromisoformat(hasta).replace(day=1)
        while actual <= fin:
            clave = f"{actual.year:04d}-{actual.month:02d}"
            datos = por_clave.get(clave, {"ventas": 0, "n_ventas": 0})
            resultado.append({"clave": clave, "etiqueta": MESES_CORTOS[actual.month - 1], **datos})
            siguiente_mes = actual.month + 1
            actual = date(actual.year + (siguiente_mes > 12), (siguiente_mes - 1) % 12 + 1, 1)
    return resultado


def granularidad_de(tipo_periodo: str) -> str:
    """'semana'/'mes' -> una barra por día; 'año'/'todo' -> una por mes."""
    return "dia" if tipo_periodo in ("semana", "mes") else "mes"


if __name__ == "__main__":
    import os
    import tempfile
    from pathlib import Path

    tmp = Path(tempfile.mkdtemp()) / "t.db"
    os.environ["SKYTEC_DB"] = str(tmp)
    database.DB_PATH = tmp
    database.init_db()

    # período sin ninguna venta: todo en cero, sin excepción
    r = resumen_periodo("2026-01-01", "2026-01-31")
    assert r == {"ventas": 0, "margen": 0, "costo": 0, "margen_pct": 0,
                 "n_ventas": 0, "ticket_promedio": 0}, r
    lineas = por_linea_negocio("2026-01-01", "2026-01-31")
    assert len(lineas) == 3
    assert all(l["ventas"] == 0 and l["participacion_pct"] == 0 for l in lineas)
    assert [l["linea_negocio"] for l in lineas] == list(LINEAS_NEGOCIO)

    # rangos de fecha
    hoy = __import__("datetime").date(2026, 9, 15)
    assert rango_periodo("mes", hoy) == ("2026-09-01", "2026-09-15")
    assert rango_periodo("semana", hoy) == ("2026-09-14", "2026-09-15")  # lunes 14
    assert rango_periodo("año", hoy) == ("2026-01-01", "2026-09-15")
    assert rango_periodo_anterior("mes", "2026-09-01", "2026-09-15") == ("2026-08-17", "2026-08-31")
    assert rango_periodo_anterior("todo", "0001-01-01", "2026-09-15") is None
    assert variacion_pct(150, 100) == 50.0
    assert variacion_pct(50, 100) == -50.0
    assert variacion_pct(10, 0) is None

    serie = serie_temporal("2026-09-01", "2026-09-03", "dia")
    assert len(serie) == 3 and all(f["ventas"] == 0 for f in serie)
    assert granularidad_de("año") == "mes" and granularidad_de("mes") == "dia"

    print("OK dashboard/repo.py")
