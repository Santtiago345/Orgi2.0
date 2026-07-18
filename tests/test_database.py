from datetime import date, timedelta
from app.database import (
    calcular_balance, obtener_rango_fechas, navegar_periodo, es_periodo_actual,
    agregar_transaccion, obtener_extractos, obtener_gastos_por_categoria,
    obtener_cuota_info, obtener_transacciones_por_periodo,
)


class TestRangoFechas:

    def test_dia(self):
        desde, hasta = obtener_rango_fechas("dia")
        assert desde == hasta == date.today()

    def test_semana(self):
        desde, hasta = obtener_rango_fechas("semana")
        hoy = date.today()
        assert desde == hoy - timedelta(days=7)
        assert hasta == hoy

    def test_mes(self):
        desde, hasta = obtener_rango_fechas("mes")
        hoy = date.today()
        assert desde == hoy.replace(day=1)
        assert hasta == hoy

    def test_anio(self):
        desde, hasta = obtener_rango_fechas("anio")
        hoy = date.today()
        assert desde == hoy.replace(month=1, day=1)
        assert hasta == hoy

    def test_personalizado(self):
        d, h = date(2026, 6, 1), date(2026, 6, 30)
        desde, hasta = obtener_rango_fechas("personalizado", d, h)
        assert desde == d
        assert hasta == h

    def test_default(self):
        desde, hasta = obtener_rango_fechas("desconocido")
        hoy = date.today()
        assert desde == hoy - timedelta(days=30)
        assert hasta == hoy


class TestEsPeriodoActual:

    def test_dia_actual(self):
        hoy = date.today()
        assert es_periodo_actual("dia", hoy, hoy) is True

    def test_dia_pasado(self):
        assert es_periodo_actual("dia", date(2025, 1, 1), date(2025, 1, 1)) is False

    def test_mes_actual(self):
        hoy = date.today()
        assert es_periodo_actual("mes", hoy.replace(day=1), hoy) is True

    def test_mes_pasado(self):
        assert es_periodo_actual("mes", date(2025, 1, 1), date(2025, 1, 31)) is False

    def test_anio_actual(self):
        hoy = date.today()
        assert es_periodo_actual("anio", hoy.replace(month=1, day=1), hoy) is True

    def test_anio_pasado(self):
        assert es_periodo_actual("anio", date(2025, 1, 1), date(2025, 12, 31)) is False


class TestNavegarPeriodo:

    def test_dia_adelante(self):
        d = date(2026, 7, 15)
        desde, hasta = navegar_periodo("dia", d, d, 1)
        assert desde == date(2026, 7, 16)
        assert hasta == date(2026, 7, 16)

    def test_dia_atras(self):
        d = date(2026, 7, 15)
        desde, hasta = navegar_periodo("dia", d, d, -1)
        assert desde == date(2026, 7, 14)

    def test_semana_adelante(self):
        d = date(2026, 7, 1)
        h = date(2026, 7, 8)
        desde, hasta = navegar_periodo("semana", d, h, 1)
        assert desde == date(2026, 7, 8)
        assert hasta == date(2026, 7, 15)

    def test_mes_adelante(self):
        d = date(2026, 7, 1)
        h = date(2026, 7, 31)
        desde, hasta = navegar_periodo("mes", d, h, 1)
        assert desde == date(2026, 8, 1)
        assert hasta == date(2026, 8, 31)

    def test_mes_atras(self):
        d = date(2026, 7, 15)
        h = date(2026, 7, 31)
        desde, hasta = navegar_periodo("mes", d, h, -1)
        assert desde == date(2026, 6, 15)
        assert hasta == date(2026, 6, 30)

    def test_mes_adelante_diciembre(self):
        d = date(2026, 12, 1)
        h = date(2026, 12, 31)
        desde, hasta = navegar_periodo("mes", d, h, 1)
        assert desde == date(2027, 1, 1)

    def test_anio_adelante(self):
        d = date(2026, 3, 15)
        h = date(2026, 8, 20)
        desde, hasta = navegar_periodo("anio", d, h, 1)
        assert desde == date(2027, 3, 15)

    def test_anio_atras(self):
        d = date(2026, 6, 1)
        h = date(2026, 6, 30)
        desde, hasta = navegar_periodo("anio", d, h, -1)
        assert desde == date(2025, 6, 1)

    def test_periodo_invalido_retorna_mismos(self):
        d = date(2026, 7, 1)
        h = date(2026, 7, 31)
        assert navegar_periodo("xyz", d, h, 1) == (d, h)


class TestBalance:

    def test_calcular_balance(self, test_db):
        balance, ingresos, gastos = calcular_balance()
        assert isinstance(balance, (int, float))
        assert isinstance(ingresos, (int, float))
        assert isinstance(gastos, (int, float))
        assert ingresos > 0
        assert gastos > 0
        total_ingresos = sum(abs(t["valor"])
                             for t in obtener_transacciones_por_periodo(
                                 "ingresos", date(2020, 1, 1), date.today()))
        total_gastos = sum(abs(t["valor"])
                           for t in obtener_transacciones_por_periodo(
                               "gastos", date(2020, 1, 1), date.today()))
        assert ingresos == round(total_ingresos)
        assert gastos >= round(total_gastos)


class TestAgregarTransaccion:

    def test_agregar_gasto(self, test_db):
        n = date.today().isoformat()
        tid = agregar_transaccion(n, "Test gasto", 50000, "Comida", "gasto")
        assert isinstance(tid, int) and tid > 0
        txs = obtener_transacciones_por_periodo("gastos", date(2020, 1, 1), date.today())
        match = [t for t in txs if t["id"] == tid]
        assert len(match) == 1
        assert match[0]["descripcion"] == "Test gasto"
        assert match[0]["valor"] < 0

    def test_agregar_ingreso(self, test_db):
        n = date.today().isoformat()
        tid = agregar_transaccion(n, "Test ingreso", 100000, "Salario", "ingreso")
        assert isinstance(tid, int) and tid > 0
        txs = obtener_transacciones_por_periodo("ingresos", date(2020, 1, 1), date.today())
        match = [t for t in txs if t["id"] == tid]
        assert len(match) == 1
        assert match[0]["valor"] > 0

    def test_agregar_con_notas(self, test_db):
        n = date.today().isoformat()
        tid = agregar_transaccion(n, "Test con notas", 75000, "Transporte",
                                  "gasto", notas="nota de prueba")
        txs = obtener_transacciones_por_periodo("gastos", date(2020, 1, 1), date.today())
        match = [t for t in txs if t["id"] == tid]
        assert match[0]["notas"] == "nota de prueba"


class TestExtractos:

    def test_obtener_extractos(self, test_db):
        extractos = obtener_extractos()
        assert len(extractos) == 2
        fuentes = {e["fuente"] for e in extractos}
        assert fuentes == {"nu", "rappicard"}

    def test_extracto_tiene_campos(self, test_db):
        e = obtener_extractos()[0]
        assert "id" in e
        assert "archivo" in e
        assert "fuente" in e
        assert "total_pagar" in e
        assert "fecha_corte" in e


class TestGastosPorCategoria:

    def test_agrupacion(self, test_db):
        cats = obtener_gastos_por_categoria("gastos", date(2026, 7, 1), date(2026, 7, 31))
        cats_map = {c["categoria"]: c for c in cats}
        assert "Comida" in cats_map
        assert cats_map["Comida"]["num_tx"] >= 2
        assert cats_map["Comida"]["total"] > 0

    def test_vacio_sin_datos(self, test_db):
        cats = obtener_gastos_por_categoria("gastos", date(2020, 1, 1), date(2020, 1, 31))
        assert len(cats) == 0


class TestCuotaInfo:

    def test_obtener_cuota_info(self, test_db):
        from app.database import get_db
        conn = get_db()
        info = obtener_cuota_info(conn)
        conn.close()
        assert isinstance(info, dict)


class TestTransaccionesPorPeriodo:

    def test_filtra_por_tipo(self, test_db):
        ingresos = obtener_transacciones_por_periodo(
            "ingresos", date(2026, 7, 1), date(2026, 7, 31))
        gastos = obtener_transacciones_por_periodo(
            "gastos", date(2026, 7, 1), date(2026, 7, 31))
        assert all(t["es_ingreso"] == 1 for t in ingresos)
        assert all(t["es_ingreso"] == 0 for t in gastos)
        assert len(ingresos) >= 2
        assert len(gastos) >= 5

    def test_rango_fechas(self, test_db):
        txs = obtener_transacciones_por_periodo(
            "gastos", date(2026, 6, 1), date(2026, 6, 30))
        assert len(txs) == 2

    def test_tags_incluidos(self, test_db):
        txs = obtener_transacciones_por_periodo(
            "gastos", date(2026, 7, 1), date(2026, 7, 31))
        for t in txs:
            assert "tags" in t
        sup = next(t for t in txs if t["descripcion"] == "Supermercado Exito")
        assert len(sup["tags"]) == 1
        assert sup["tags"][0]["nombre"] == "recurrente"
