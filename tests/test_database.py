import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date
from app.database import (
    calcular_balance, obtener_rango_fechas, es_periodo_actual,
)


def test_obtener_rango_fechas_dia():
    desde, hasta = obtener_rango_fechas("dia")
    assert desde == hasta == date.today()


def test_obtener_rango_fechas_mes():
    desde, hasta = obtener_rango_fechas("mes")
    hoy = date.today()
    assert desde == hoy.replace(day=1)
    assert hasta == hoy


def test_es_periodo_actual():
    hoy = date.today()
    assert es_periodo_actual("dia", hoy, hoy) == True
    assert es_periodo_actual("dia", date(2020, 1, 1), date(2020, 1, 1)) == False


def test_calcular_balance():
    balance, ingresos, gastos = calcular_balance()
    assert isinstance(balance, (int, float))
    assert isinstance(ingresos, (int, float))
    assert isinstance(gastos, (int, float))
    assert ingresos >= 0
    assert gastos >= 0


if __name__ == "__main__":
    test_obtener_rango_fechas_dia()
    test_obtener_rango_fechas_mes()
    test_es_periodo_actual()
    test_calcular_balance()
    print("All tests passed!")
