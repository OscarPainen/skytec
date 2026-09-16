"""Dashboard (Fase 2): agregaciones sobre v_operaciones con datos sembrados y
valores esperados calculados A MANO (no con la misma consulta que se prueba).
"""
from __future__ import annotations

from core import database
from modules.dashboard import repo as dash


def _venta(conn, fecha: str, pos_origen: str, origen: str, items: list[dict]) -> int:
    """Inserta una venta + sus ítems directamente por SQL (no vía pos.repo,
    que no deja fijar `fecha`: acá necesitamos fechas controladas para
    separar "este mes" de "el mes pasado")."""
    total = sum(it["cantidad"] * it["precio_unitario"] for it in items)
    cur = conn.execute(
        "INSERT INTO ventas (tipo, total, fecha, pos_origen, origen) VALUES (?,?,?,?,?)",
        ("directa", total, fecha, pos_origen, origen),
    )
    venta_id = cur.lastrowid
    for it in items:
        subtotal = it["cantidad"] * it["precio_unitario"]
        conn.execute(
            "INSERT INTO venta_items (venta_id, cantidad, precio_unitario, subtotal, "
            "categoria, linea_negocio, costo_unitario) VALUES (?,?,?,?,?,?,?)",
            (venta_id, it["cantidad"], it["precio_unitario"], subtotal,
             it["categoria"], it["linea_negocio"], it["costo_unitario"]),
        )
    conn.commit()
    return venta_id


def _sembrar(conn) -> None:
    # Septiembre 2026 (período "actual" en los tests)
    _venta(conn, "2026-09-05 10:00:00", "Tech", "pos", [
        {"cantidad": 1, "precio_unitario": 10000, "costo_unitario": 4000,
         "categoria": "Accesorios", "linea_negocio": "tecnologia"},
    ])
    _venta(conn, "2026-09-10 11:00:00", "Tech", "pos", [
        {"cantidad": 2, "precio_unitario": 5000, "costo_unitario": 2000,
         "categoria": "Proteínas", "linea_negocio": "suplemento"},
    ])
    _venta(conn, "2026-09-12 12:00:00", "Fit", "agenda", [
        {"cantidad": 1, "precio_unitario": 45000, "costo_unitario": 0,
         "categoria": "reparacion", "linea_negocio": "reparacion"},
    ])
    # Agosto 2026 (período "anterior")
    _venta(conn, "2026-08-10 09:00:00", "Tech", "pos", [
        {"cantidad": 1, "precio_unitario": 5000, "costo_unitario": 1000,
         "categoria": "Accesorios", "linea_negocio": "tecnologia"},
    ])


def test_resumen_periodo_con_datos_conocidos(db_temporal):
    conn = database.get_connection()
    _sembrar(conn)
    conn.close()

    # Septiembre: ventas 10000+10000+45000=65000; margen 6000+6000+45000=57000;
    # 3 ventas distintas; ticket promedio 65000/3=21666.67 -> redondea a 21667
    r = dash.resumen_periodo("2026-09-01", "2026-09-30")
    assert r["ventas"] == 65000
    assert r["margen"] == 57000
    assert r["costo"] == 8000  # 4000 (tecnologia) + 4000 (suplemento) + 0 (reparacion)
    assert r["margen_pct"] == round(57000 / 65000 * 100, 1)
    assert r["n_ventas"] == 3
    assert r["ticket_promedio"] == 21667

    # Agosto: una sola venta de 5000, margen 4000, costo 1000 (no es 0)
    r_ago = dash.resumen_periodo("2026-08-01", "2026-08-31")
    assert r_ago == {
        "ventas": 5000, "margen": 4000, "costo": 1000, "margen_pct": 80.0,
        "n_ventas": 1, "ticket_promedio": 5000,
    }


def test_resumen_periodo_margen_pct_none_sin_costos_cargados(db_temporal):
    """Problema 2 del rediseño: con ventas > 0 pero costo total = 0, el
    margen no puede decir "100%" — no hay costos cargados para saberlo."""
    conn = database.get_connection()
    _venta(conn, "2026-09-05 10:00:00", "Tech", "pos", [
        {"cantidad": 1, "precio_unitario": 10000, "costo_unitario": 0,
         "categoria": "Accesorios", "linea_negocio": "tecnologia"},
    ])
    conn.close()
    r = dash.resumen_periodo("2026-09-01", "2026-09-30")
    assert r["ventas"] == 10000
    assert r["costo"] == 0
    assert r["margen_pct"] is None


def test_por_linea_negocio_con_datos_conocidos(db_temporal):
    conn = database.get_connection()
    _sembrar(conn)
    conn.close()

    lineas = {l["linea_negocio"]: l for l in dash.por_linea_negocio("2026-09-01", "2026-09-30")}
    assert set(lineas) == {"reparacion", "tecnologia", "suplemento"}

    assert lineas["tecnologia"]["ventas"] == 10000
    assert lineas["tecnologia"]["margen"] == 6000
    assert lineas["tecnologia"]["n_items"] == 1

    assert lineas["suplemento"]["ventas"] == 10000
    assert lineas["suplemento"]["margen"] == 6000

    assert lineas["reparacion"]["ventas"] == 45000
    assert lineas["reparacion"]["margen"] == 45000

    # participación sobre el total de 65000
    assert lineas["reparacion"]["participacion_pct"] == round(45000 / 65000 * 100, 1)
    assert lineas["tecnologia"]["participacion_pct"] == round(10000 / 65000 * 100, 1)


def test_por_caja_con_datos_conocidos(db_temporal):
    conn = database.get_connection()
    _sembrar(conn)
    conn.close()

    cajas = {c["caja"]: c for c in dash.por_caja("2026-09-01", "2026-09-30")}
    assert cajas["Tech"]["ventas"] == 20000  # las dos ventas de Tech
    assert cajas["Tech"]["n_ventas"] == 2
    assert cajas["Fit"]["ventas"] == 45000
    assert cajas["Fit"]["n_ventas"] == 1


def test_por_categoria_filtra_por_linea(db_temporal):
    conn = database.get_connection()
    _sembrar(conn)
    conn.close()

    cats = dash.por_categoria("tecnologia", "2026-09-01", "2026-09-30")
    assert len(cats) == 1
    assert cats[0]["categoria"] == "Accesorios"
    assert cats[0]["ventas"] == 10000


def test_periodo_sin_ventas_devuelve_ceros_en_las_tres_lineas(db_temporal):
    """Caso borde explícito que pide el plan: sin datos, ceros, sin excepción."""
    r = dash.resumen_periodo("2030-01-01", "2030-01-31")
    assert r == {"ventas": 0, "margen": 0, "costo": 0, "margen_pct": 0,
                 "n_ventas": 0, "ticket_promedio": 0}

    lineas = dash.por_linea_negocio("2030-01-01", "2030-01-31")
    assert len(lineas) == 3
    assert all(l["ventas"] == 0 and l["margen"] == 0 and l["n_items"] == 0
               and l["participacion_pct"] == 0 for l in lineas)

    assert dash.por_caja("2030-01-01", "2030-01-31") == []
    assert dash.por_categoria("tecnologia", "2030-01-01", "2030-01-31") == []


def test_rango_periodo_y_anterior():
    from datetime import date
    hoy = date(2026, 9, 15)

    assert dash.rango_periodo("mes", hoy) == ("2026-09-01", "2026-09-15")
    assert dash.rango_periodo("semana", hoy) == ("2026-09-14", "2026-09-15")
    assert dash.rango_periodo("año", hoy) == ("2026-01-01", "2026-09-15")

    desde, hasta = dash.rango_periodo("mes", hoy)
    assert dash.rango_periodo_anterior("mes", desde, hasta) == ("2026-08-17", "2026-08-31")
    assert dash.rango_periodo_anterior("todo", "0001-01-01", "2026-09-15") is None


def test_variacion_pct():
    assert dash.variacion_pct(150, 100) == 50.0
    assert dash.variacion_pct(50, 100) == -50.0
    assert dash.variacion_pct(10, 0) is None
    assert dash.variacion_pct(0, 0) is None


def test_granularidad_de():
    assert dash.granularidad_de("semana") == "dia"
    assert dash.granularidad_de("mes") == "dia"
    assert dash.granularidad_de("año") == "mes"
    assert dash.granularidad_de("todo") == "mes"


def test_serie_temporal_por_dia_incluye_dias_sin_ventas(db_temporal):
    conn = database.get_connection()
    _venta(conn, "2026-09-05 10:00:00", "Tech", "pos", [
        {"cantidad": 1, "precio_unitario": 10000, "costo_unitario": 4000,
         "categoria": "Accesorios", "linea_negocio": "tecnologia"},
    ])
    conn.close()

    serie = dash.serie_temporal("2026-09-01", "2026-09-05", "dia")
    assert len(serie) == 5, "1 al 5 de septiembre inclusive, sin saltarse ninguno"
    assert [f["clave"] for f in serie] == [
        "2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04", "2026-09-05",
    ]
    assert [f["ventas"] for f in serie] == [0, 0, 0, 0, 10000]
    assert serie[-1]["etiqueta"] == "5"
    assert serie[-1]["n_ventas"] == 1
    assert serie[0]["n_ventas"] == 0  # día sin ventas: 0, no ausente


def test_serie_temporal_por_mes(db_temporal):
    conn = database.get_connection()
    _venta(conn, "2026-09-05 10:00:00", "Tech", "pos", [
        {"cantidad": 1, "precio_unitario": 10000, "costo_unitario": 4000,
         "categoria": "Accesorios", "linea_negocio": "tecnologia"},
    ])
    conn.close()

    serie = dash.serie_temporal("2026-07-01", "2026-09-30", "mes")
    assert [f["clave"] for f in serie] == ["2026-07", "2026-08", "2026-09"]
    assert [f["etiqueta"] for f in serie] == ["Jul", "Ago", "Sep"]
    assert [f["ventas"] for f in serie] == [0, 0, 10000]


def test_serie_temporal_granularidad_invalida():
    import pytest
    with pytest.raises(ValueError):
        dash.serie_temporal("2026-01-01", "2026-01-02", "hora")
