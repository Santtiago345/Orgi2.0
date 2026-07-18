def normalize_valor(valor, tipo=None, es_ingreso=None):
    """Normaliza el signo del valor: ingresos positivos, gastos negativos.

    - Si `es_ingreso` es 1/0 lo prioriza.
    - Si `tipo` contiene 'income'/'ingreso' lo trata como ingreso.
    - Si `tipo` contiene 'expense'/'gasto' lo trata como gasto.
    - Si ninguno está presente, usa el signo actual: mantiene positivo/negativo.
    """
    try:
        v = float(valor)
    except Exception:
        return valor

    # Priorizar es_ingreso si provisto
    if es_ingreso is not None:
        try:
            if int(es_ingreso) == 1:
                return abs(v)
            else:
                return -abs(v)
        except Exception:
            pass

    # Priorizar tipo textual
    if tipo:
        t = str(tipo).lower()
        if 'income' in t or 'ingreso' in t:
            return abs(v)
        if 'expense' in t or 'gasto' in t:
            return -abs(v)

    # Fallback: no change
    return v