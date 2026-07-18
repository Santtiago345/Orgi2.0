import sqlite3, os
from datetime import datetime, timedelta, date

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE, "data", "final_finanzas.db")
DB_COMPLETA = os.path.join(BASE, "data", "final_finanzas.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_db_completa():
    conn = sqlite3.connect(DB_COMPLETA)
    conn.row_factory = sqlite3.Row
    return conn

def calcular_balance():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COALESCE(SUM(valor),0) FROM transacciones WHERE es_ingreso=1")
    ingresos = c.fetchone()[0]
    
    c.execute("SELECT COALESCE(SUM(ABS(valor)),0) FROM transacciones WHERE es_ingreso=0 AND valor < 0")
    gastos = c.fetchone()[0]
    
    c.execute("SELECT COALESCE(SUM(ABS(valor_total)),0) FROM compras_diferidas")
    gastos += c.fetchone()[0]
    
    conn.close()
    return round(ingresos - gastos), round(ingresos), round(gastos)

def obtener_rango_fechas(periodo, desde=None, hasta=None):
    hoy = date.today()
    if periodo == "dia":
        return hoy, hoy
    elif periodo == "semana":
        return hoy - timedelta(days=7), hoy
    elif periodo == "mes":
        return hoy.replace(day=1), hoy
    elif periodo == "anio":
        return hoy.replace(month=1, day=1), hoy
    elif periodo == "personalizado" and desde and hasta:
        return desde, hasta
    return hoy - timedelta(days=30), hoy

def navegar_periodo(periodo, desde, hasta, direccion):
    if periodo == "dia":
        d = desde + timedelta(days=direccion)
        return d, d
    elif periodo == "semana":
        return desde + timedelta(days=7*direccion), hasta + timedelta(days=7*direccion)
    elif periodo == "mes":
        m = desde.month - 1 + direccion
        y = desde.year + m // 12
        m = m % 12 + 1
        import calendar
        last = calendar.monthrange(y, m)[1]
        nd = desde.replace(year=y, month=m, day=min(desde.day, last))
        nh = nd.replace(day=last) if hasta > desde else nd
        if nh > date.today():
            nh = date.today()
        return nd, nh
    elif periodo == "anio":
        ny = desde.year + direccion
        nd = desde.replace(year=ny)
        nh = hasta.replace(year=ny) if hasta else nd
        if nh > date.today():
            nh = date.today()
        return nd, nh
    return desde, hasta

def es_periodo_actual(periodo, desde, hasta):
    hoy = date.today()
    if periodo == "dia":
        return desde == hoy
    elif periodo == "semana":
        return hasta >= hoy - timedelta(days=1)
    elif periodo == "mes":
        return desde.month == hoy.month and desde.year == hoy.year
    elif periodo == "anio":
        return desde.year == hoy.year
    return True

def obtener_transacciones_por_periodo(tipo, fecha_desde, fecha_hasta):
    es_ingreso = 1 if tipo == "ingresos" else 0
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT id, fecha, fecha_date, descripcion, valor, categoria, entidad, es_ingreso, notas, extracto_id, metodo_pago
        FROM transacciones
        WHERE es_ingreso=? AND fecha_date >= ? AND fecha_date <= ?
        ORDER BY fecha_date DESC
    """, (es_ingreso, fecha_desde.isoformat(), fecha_hasta.isoformat()))
    rows = [dict(r) for r in c.fetchall()]
    for r in rows:
        r['tags'] = obtener_etiquetas_transaccion(conn, r['id'])
    conn.close()
    return rows

def obtener_gastos_por_categoria(tipo, fecha_desde, fecha_hasta):
    es_ingreso = 1 if tipo == "ingresos" else 0
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT categoria, COUNT(*) as num_tx, COALESCE(SUM(ABS(valor)),0) as total
        FROM transacciones
        WHERE es_ingreso=? AND fecha_date >= ? AND fecha_date <= ?
        GROUP BY categoria
        ORDER BY total DESC
    """, (es_ingreso, fecha_desde.isoformat(), fecha_hasta.isoformat()))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def agregar_transaccion(fecha, descripcion, valor, categoria, tipo, notas="", entidad="manual", metodo_pago="transferencia"):
    es_ingreso = 1 if tipo == "ingreso" else 0
    conn = get_db()
    c = conn.cursor()
    # Normalizar signo: almacenar ingresos como valores positivos y gastos como negativos
    try:
        v = float(valor)
    except Exception:
        v = valor
    if es_ingreso:
        if isinstance(v, (int, float)) and v < 0:
            v = abs(v)
    else:
        if isinstance(v, (int, float)) and v > 0:
            v = -abs(v)

    c.execute("""
        INSERT INTO transacciones (fecha, fecha_date, descripcion, valor, categoria, entidad, es_ingreso, notas, metodo_pago)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (fecha, fecha, descripcion, v, categoria, entidad, es_ingreso, notas, metodo_pago))
    conn.commit()
    new_id = c.lastrowid
    conn.close()
    return new_id

def obtener_ultima_fecha():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT MAX(fecha_date) FROM transacciones")
    r = c.fetchone()[0]
    conn.close()
    return r or date.today().isoformat()

def obtener_extractos():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT id, archivo, fuente, tipo, periodo, anio, mes,
               titular, total_pagar, pago_minimo, cupo_total, saldo_anterior,
               fecha_corte, fecha_pago, num_transacciones
        FROM extractos
        ORDER BY fuente, anio DESC, mes DESC
    """)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def buscar_extracto_duplicado(archivo_nombre):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM extractos WHERE archivo LIKE ?", (f"%{archivo_nombre}%",))
    count = c.fetchone()[0]
    conn.close()
    return count > 0

# ─── CUOTA DETECTION ─────────────────────────────────────────

def obtener_cuota_info(conn=None):
    """Return {transaccion_id: {cuota_actual, total_cuotas, compra_desc, valor_total}}
    for all TC transactions that are part of a cuota plan."""
    own_conn = False
    if conn is None:
        conn = get_db()
        own_conn = True
    c = conn.cursor()
    info = {}
    try:
        # Join transacciones -> cuotas_tc -> compras_tc via extracto_id + valor match + normalized descripcion
        c.execute("""
            SELECT t.id as tx_id,
                   c.cuota_numero as cuota_actual,
                   cp.total_cuotas,
                   cp.valor_total,
                   cp.descripcion as compra_desc
            FROM transacciones t
            JOIN cuotas_tc c ON t.extracto_id = c.extracto_id
                AND ROUND(ABS(t.valor)) = ROUND(ABS(c.capital_facturado))
            JOIN compras_tc cp ON c.compra_id = cp.id
                AND UPPER(TRIM(t.descripcion)) = cp.descripcion
            WHERE t.entidad IN ('nu','rappicard')
              AND t.valor < 0
        """)
        for r in c.fetchall():
            info[r['tx_id']] = {
                'cuota_actual': r['cuota_actual'],
                'total_cuotas': r['total_cuotas'],
                'compra_desc': r['compra_desc'],
                'valor_total': r['valor_total'],
            }
    except sqlite3.OperationalError:
        # tablas relacionadas con cuotas no existen en esta BD -> devolver vacío
        return {}
    if own_conn:
        conn.close()
    return info

# ─── ETIQUETAS ────────────────────────────────────────────────

def obtener_etiquetas():
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("SELECT * FROM etiquetas ORDER BY nombre")
        rows = [dict(r) for r in c.fetchall()]
    except sqlite3.OperationalError:
        rows = []
    conn.close()
    return rows

def crear_etiqueta(nombre, color="#6B7280"):
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO etiquetas (nombre, color) VALUES (?, ?)", (nombre, color))
        conn.commit()
        new_id = c.lastrowid
        conn.close()
        return new_id, None
    except sqlite3.IntegrityError:
        conn.close()
        return None, "Ya existe una etiqueta con ese nombre"

def actualizar_etiqueta(eid, nombre, color):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE etiquetas SET nombre=?, color=? WHERE id=?", (nombre, color, eid))
    conn.commit()
    conn.close()
    return c.rowcount > 0

def eliminar_etiqueta(eid):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM transaccion_etiquetas WHERE etiqueta_id=?", (eid,))
    c.execute("DELETE FROM etiquetas WHERE id=?", (eid,))
    conn.commit()
    conn.close()
    return c.rowcount > 0

def obtener_etiquetas_transaccion(conn, transaccion_id):
    c = conn.cursor()
    try:
        c.execute("""
            SELECT e.id, e.nombre, e.color
            FROM etiquetas e
            JOIN transaccion_etiquetas te ON te.etiqueta_id = e.id
            WHERE te.transaccion_id = ?
            ORDER BY e.nombre
        """, (transaccion_id,))
        return [dict(r) for r in c.fetchall()]
    except sqlite3.OperationalError:
        return []

def asignar_etiqueta(transaccion_id, etiqueta_id):
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO transaccion_etiquetas (transaccion_id, etiqueta_id) VALUES (?, ?)",
                  (transaccion_id, etiqueta_id))
        conn.commit()
        ok = True
    except sqlite3.IntegrityError:
        ok = False
    conn.close()
    return ok

def quitar_etiqueta(transaccion_id, etiqueta_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM transaccion_etiquetas WHERE transaccion_id=? AND etiqueta_id=?",
              (transaccion_id, etiqueta_id))
    conn.commit()
    conn.close()
    return c.rowcount > 0

# ─── CATEGORIAS ──────────────────────────────────────────────

def obtener_categorias_lista():
    """Return distinct categories from transacciones (our source of truth)."""
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT categoria, COUNT(*) as total_tx,
               COALESCE(SUM(ABS(valor)),0) as total_gastado
        FROM transacciones WHERE es_ingreso=0
        GROUP BY categoria ORDER BY total_gastado DESC
    """)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def obtener_transacciones_por_categoria(categoria, fecha_desde=None, fecha_hasta=None, metodo_pago=None, orden="fecha", desc=True):
    """Get transactions filtered by category with optional filters."""
    conn = get_db()
    c = conn.cursor()
    params = [categoria]
    sql = """
        SELECT id, fecha, fecha_date, descripcion, valor, entidad, es_ingreso, notas, metodo_pago
        FROM transacciones WHERE categoria = ?
    """
    if fecha_desde:
        sql += " AND fecha_date >= ?"
        params.append(fecha_desde.isoformat())
    if fecha_hasta:
        sql += " AND fecha_date <= ?"
        params.append(fecha_hasta.isoformat())
    if metodo_pago:
        pagos = metodo_pago.split(',')
        placeholders = ','.join('?' for _ in pagos)
        sql += f" AND metodo_pago IN ({placeholders})"
        params.extend(pagos)

    dir_sql = "DESC" if desc else "ASC"
    if orden == "fecha":
        sql += f" ORDER BY fecha_date {dir_sql}"
    elif orden == "valor":
        sql += f" ORDER BY ABS(valor) {dir_sql}"

    c.execute(sql, params)
    rows = [dict(r) for r in c.fetchall()]
    for r in rows:
        r['tags'] = obtener_etiquetas_transaccion(conn, r['id'])
    conn.close()
    return rows

# ─── CREDIT PROFILE ──────────────────────────────────────────

def obtener_perfil_crediticia():
    """Return credit card info and credit data for the credit profile page.
    La deuda total se calcula con base en el ÚLTIMO extracto, no la suma histórica."""
    conn = get_db()
    c = conn.cursor()

    # Obtener el último extracto de cada tarjeta para la deuda actual
    c.execute("""
        SELECT e.fuente,
               COUNT(*) as num_extractos,
               MAX(COALESCE(e.anio,0)*100+COALESCE(e.mes,0)) as ultimo_periodo,
               e_last.total_pagar as deuda_total,
               e_last.pago_minimo as pago_minimo_total,
               e_last.cupo_total,
               e_last.saldo_anterior,
               e_last.total_cargos,
               e_last.total_abonos,
               e_last.fecha_corte,
               e_last.fecha_pago,
               e_last.anio as ultimo_anio,
               e_last.mes as ultimo_mes
        FROM extractos e
        JOIN extractos e_last ON e_last.fuente = e.fuente
            AND COALESCE(e_last.anio,0)*100+COALESCE(e_last.mes,0) = (SELECT MAX(COALESCE(ei.anio,0)*100+COALESCE(ei.mes,0)) FROM extractos ei WHERE ei.fuente = e.fuente)
        WHERE e.fuente IN ('nu','rappicard')
        GROUP BY e.fuente
    """)
    tarjetas = [dict(r) for r in c.fetchall()]

    c.execute("""
        SELECT id, archivo, fuente, periodo, anio, mes,
               total_pagar, pago_minimo, cupo_total, saldo_anterior,
               saldo_actual, total_cargos, total_abonos,
               fecha_corte, fecha_pago, titular,
               interes_corriente, tasa_mensual, tasa_anual_ea
        FROM extractos
        WHERE fuente IN ('nu','rappicard')
        ORDER BY fuente, anio DESC, mes DESC
    """)
    extractos_tc = [dict(r) for r in c.fetchall()]
    conn.close()

    return {
        "tarjetas": tarjetas,
        "extractos": extractos_tc,
    }


def obtener_prestamos_nequi():
    """Devuelve los préstamos de Nequi agrupados individualmente con sus pagos.
    Identifica desembolsos y asocia pagos subsecuentes a cada préstamo."""
    NEQUI_DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            'data', 'nequi', 'nequi_finanzas.db')
    if not os.path.exists(NEQUI_DB):
        return []

    try:
        conn = sqlite3.connect(NEQUI_DB)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        # Obtener desembolsos ordenados cronológicamente
        c.execute("""
            SELECT fecha_date, descripcion_normalizada, valor, id
            FROM transacciones
            WHERE (descripcion_normalizada LIKE '%DESEMBOLSO%PRESTAMO%'
                OR descripcion_normalizada LIKE '%DESEMBOLSO%CREDITO%')
              AND valor > 0
            ORDER BY fecha_date ASC
        """)
        desembolsos = [dict(r) for r in c.fetchall()]

        # Obtener todos los pagos de préstamos
        c.execute("""
            SELECT fecha_date, descripcion_normalizada, valor, id
            FROM transacciones
            WHERE (descripcion_normalizada LIKE '%PAGO%PRESTAMO%'
                OR descripcion_normalizada LIKE '%PAGO%CREDITO%'
                OR descripcion_normalizada LIKE '%PAGO TOTAL%')
              AND valor < 0
            ORDER BY fecha_date ASC
        """)
        pagos_todos = [dict(r) for r in c.fetchall()]
        conn.close()

        # Agrupar pagos a cada préstamo: el pago va al préstamo más reciente antes de la fecha del pago
        prestamos = []
        for i, des in enumerate(desembolsos):
            fecha_inicio = des['fecha_date']
            fecha_fin = desembolsos[i+1]['fecha_date'] if i+1 < len(desembolsos) else '9999-12-31'

            pagos_prestamo = [
                p for p in pagos_todos
                if fecha_inicio <= p['fecha_date'] < fecha_fin
            ]

            total_pagado = sum(abs(p['valor']) for p in pagos_prestamo)
            monto_prestado = des['valor']
            saldo_pendiente = max(0, monto_prestado - total_pagado)
            estado = 'pagado' if saldo_pendiente == 0 else 'activo'

            prestamos.append({
                'fecha_desembolso': des['fecha_date'],
                'descripcion': des['descripcion_normalizada'],
                'monto_prestado': monto_prestado,
                'total_pagado': total_pagado,
                'saldo_pendiente': saldo_pendiente,
                'num_pagos': len(pagos_prestamo),
                'estado': estado,
                'pagos': [{
                    'fecha': p['fecha_date'],
                    'descripcion': p['descripcion_normalizada'],
                    'valor': abs(p['valor'])
                } for p in pagos_prestamo]
            })

        return sorted(prestamos, key=lambda x: x['fecha_desembolso'], reverse=True)
    except Exception:
        return []

def obtener_extracto_detalle(extracto_id):
    conn = get_db()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("SELECT * FROM extractos WHERE id=?", (extracto_id,))
    extr = c.fetchone()
    if not extr:
        conn.close()
        return None
    extr = dict(extr)

    c.execute("""
        SELECT id, fecha, fecha_date, descripcion, valor, categoria, entidad, es_ingreso, notas, metodo_pago, 'transaccion' as tipo_registro
        FROM transacciones
        WHERE extracto_id=?
        UNION ALL
        SELECT ct.id, cd.fecha as fecha, cd.fecha as fecha_date, 
               cd.descripcion || ' (' || ct.num_cuota || '/' || cd.total_cuotas || ')' as descripcion,
               -ABS(ct.valor_cuota) as valor, cd.categoria, cd.fuente as entidad, 0 as es_ingreso, '' as notas, 'tarjeta' as metodo_pago, 'cuota' as tipo_registro
        FROM cuotas_tarjeta ct
        JOIN compras_diferidas cd ON ct.compra_diferida_id = cd.id
        WHERE ct.extracto_id=?
        ORDER BY fecha_date DESC
    """, (extracto_id, extracto_id))
    txs = [dict(r) for r in c.fetchall()]
    for t in txs:
        t['tags'] = obtener_etiquetas_transaccion(conn, t['id']) if t['tipo_registro'] == 'transaccion' else []

    ingresos = [t for t in txs if t['es_ingreso'] == 1]
    gastos = [t for t in txs if t['es_ingreso'] == 0]
    total_ingresos = round(sum(t['valor'] for t in ingresos))
    total_gastos = round(sum(abs(t['valor']) for t in gastos))

    cuotas = []
    if extr['fuente'] in ('rappicard', 'nu'):
        desc_counts = {}
        for t in txs:
            key = (t['descripcion'].strip().lower(), abs(t['valor']))
            desc_counts[key] = desc_counts.get(key, 0) + 1
        multi = {k for k, v in desc_counts.items() if v > 1}
        for t in txs:
            key = (t['descripcion'].strip().lower(), abs(t['valor']))
            if key in multi:
                cuotas.append(t)

    conn.close()
    return {
        "extracto": extr,
        "transacciones": txs,
        "ingresos": ingresos,
        "gastos": gastos,
        "total_ingresos": total_ingresos,
        "total_gastos": total_gastos,
        "num_ingresos": len(ingresos),
        "num_gastos": len(gastos),
        "cuotas": cuotas,
        "num_cuotas": len(set((t['descripcion'], abs(t['valor'])) for t in cuotas)),
    }

def actualizar_nota(transaccion_id, notas):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE transacciones SET notas=? WHERE id=?", (notas, transaccion_id))
    conn.commit()
    conn.close()
    return c.rowcount > 0

def actualizar_categoria_tx(transaccion_id, categoria):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE transacciones SET categoria=? WHERE id=?", (categoria, transaccion_id))
    conn.commit()
    conn.close()
    return c.rowcount > 0

def renombrar_categoria(viejo, nuevo):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE transacciones SET categoria=? WHERE categoria=?", (nuevo, viejo))
    conn.commit()
    cambios = c.rowcount
    conn.close()
    return cambios

def obtener_config_categorias():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM config_categorias")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def guardar_config_categoria(nombre, icono, color):
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO config_categorias (nombre, icono, color)
        VALUES (?, ?, ?)
        ON CONFLICT(nombre) DO UPDATE SET icono=excluded.icono, color=excluded.color
    """, (nombre, icono, color))
    conn.commit()
    conn.close()
    return True

# ─── PRESUPUESTOS ─────────────────────────────────────────

def _init_presupuestos():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS presupuestos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            categoria TEXT NOT NULL,
            monto REAL NOT NULL,
            mes INTEGER NOT NULL,
            anio INTEGER NOT NULL,
            UNIQUE(categoria, mes, anio)
        )
    """)
    conn.commit()
    conn.close()

def obtener_presupuestos():
    _init_presupuestos()
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM presupuestos ORDER BY categoria")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def guardar_presupuesto(categoria, monto, mes, anio):
    _init_presupuestos()
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO presupuestos (categoria, monto, mes, anio)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(categoria, mes, anio) DO UPDATE SET monto=excluded.monto
    """, (categoria, monto, mes, anio))
    conn.commit()
    new_id = c.lastrowid
    conn.close()
    return new_id

def eliminar_presupuesto(id):
    _init_presupuestos()
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM presupuestos WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return c.rowcount > 0

def obtener_resumen_presupuesto(mes, anio):
    _init_presupuestos()
    conn = get_db()
    c = conn.cursor()

    # Obtener presupuestos para el mes/año
    c.execute("SELECT * FROM presupuestos WHERE mes=? AND anio=?", (mes, anio))
    presupuestos = [dict(r) for r in c.fetchall()]

    # Obtener gastos reales por categoría para el mismo período
    import calendar
    last_day = calendar.monthrange(anio, mes)[1]
    desde = f"{anio:04d}-{mes:02d}-01"
    hasta = f"{anio:04d}-{mes:02d}-{last_day:02d}"

    c.execute("""
        SELECT categoria, COALESCE(SUM(ABS(valor)),0) as gastado
        FROM transacciones
        WHERE es_ingreso=0 AND fecha_date >= ? AND fecha_date <= ?
        GROUP BY categoria
    """, (desde, hasta))
    gastos = {r["categoria"]: r["gastado"] for r in c.fetchall()}

    conn.close()

    resultado = []
    for p in presupuestos:
        gastado = round(gastos.get(p["categoria"], 0))
        monto = round(p["monto"])
        pct = round(gastado / monto * 100, 1) if monto > 0 else 0
        if pct > 100:
            estado = "excedido"
        elif pct >= 80:
            estado = "advertencia"
        else:
            estado = "ok"
        resultado.append({
            "id": p["id"],
            "categoria": p["categoria"],
            "monto": monto,
            "monto_fmt": f"${monto:,}".replace(",", "."),
            "gastado": gastado,
            "gastado_fmt": f"${gastado:,}".replace(",", "."),
            "porcentaje": pct,
            "estado": estado,
        })

    return resultado

# ─── REPORTES ─────────────────────────────────────────────

def obtener_tendencia_mensual(meses=12):
    conn = get_db()
    c = conn.cursor()
    from datetime import date as dt_date
    hoy = dt_date.today()
    desde_mes = hoy.month - meses + 1
    desde_anio = hoy.year
    while desde_mes <= 0:
        desde_mes += 12
        desde_anio -= 1
    desde = f"{desde_anio:04d}-{desde_mes:02d}-01"

    c.execute("""
        SELECT
            strftime('%Y', fecha_date) as anio,
            strftime('%m', fecha_date) as mes,
            COALESCE(SUM(CASE WHEN es_ingreso=1 THEN valor ELSE 0 END),0) as ingresos,
            COALESCE(SUM(CASE WHEN es_ingreso=0 THEN ABS(valor) ELSE 0 END),0) as gastos
        FROM transacciones
        WHERE fecha_date >= ?
        GROUP BY anio, mes
        ORDER BY anio, mes
    """, (desde,))
    rows = [dict(r) for r in c.fetchall()]
    for r in rows:
        r["ingresos"] = round(r["ingresos"])
        r["gastos"] = round(r["gastos"])
        r["balance"] = r["ingresos"] - r["gastos"]
    conn.close()
    return rows

def obtener_comparativa_anual(anio):
    conn = get_db()
    c = conn.cursor()
    anio_ant = anio - 1

    def _gastos_por_categoria(anio_ref):
        c.execute("""
            SELECT categoria, COALESCE(SUM(ABS(valor)),0) as total
            FROM transacciones
            WHERE es_ingreso=0 AND strftime('%Y', fecha_date) = ?
            GROUP BY categoria
            ORDER BY total DESC
        """, (str(anio_ref),))
        return {r["categoria"]: round(r["total"]) for r in c.fetchall()}

    actual = _gastos_por_categoria(anio)
    anterior = _gastos_por_categoria(anio_ant)

    todas_cats = sorted(set(list(actual.keys()) + list(anterior.keys())))
    resultado = []
    for cat in todas_cats:
        ga = actual.get(cat, 0)
        ant = anterior.get(cat, 0)
        diff = ga - ant
        pct = round(diff / ant * 100, 1) if ant > 0 else (100 if ga > 0 else 0)
        resultado.append({
            "categoria": cat,
            "actual": ga,
            "actual_fmt": f"${ga:,}".replace(",", "."),
            "anterior": ant,
            "anterior_fmt": f"${ant:,}".replace(",", "."),
            "diferencia": diff,
            "diferencia_fmt": f"${diff:,}".replace(",", "."),
            "porcentaje_cambio": pct,
        })

    conn.close()
    return resultado

def obtener_top_gastos(limite=10, desde=None, hasta=None):
    conn = get_db()
    c = conn.cursor()
    params = []
    sql = """
        SELECT id, fecha, fecha_date, descripcion, valor, categoria, entidad, notas, metodo_pago
        FROM transacciones
        WHERE es_ingreso=0 AND valor < 0
    """
    if desde:
        sql += " AND fecha_date >= ?"
        params.append(desde)
    if hasta:
        sql += " AND fecha_date <= ?"
        params.append(hasta)
    sql += " ORDER BY ABS(valor) DESC LIMIT ?"
    params.append(limite)

    c.execute(sql, params)
    rows = [dict(r) for r in c.fetchall()]
    for r in rows:
        r["valor_abs"] = round(abs(r["valor"]))
        r["valor_fmt"] = f"${r['valor_abs']:,}".replace(",", ".")
    conn.close()
    return rows

# ─── CRUCE ─────────────────────────────────────────────────

def obtener_sin_cruzar(entidad=None, categoria=None, limite=50, offset=0):
    conn = get_db()
    c = conn.cursor()
    params = []
    sql = """
        SELECT id, fecha, fecha_date, descripcion, valor, entidad, categoria, es_ingreso, metodo_pago, notas
        FROM transacciones
        WHERE cruzada = 0
    """
    if entidad and entidad != 'todas':
        sql += " AND entidad = ?"
        params.append(entidad)
    if categoria:
        sql += " AND categoria = ?"
        params.append(categoria)

    count_sql = sql.replace("SELECT id, fecha, fecha_date, descripcion, valor, entidad, categoria, es_ingreso, metodo_pago, notas", "SELECT COUNT(*)")
    c.execute(count_sql, params)
    total = c.fetchone()[0]

    sql += " ORDER BY fecha_date DESC LIMIT ? OFFSET ?"
    params.extend([limite, offset])
    c.execute(sql, params)
    rows = [dict(r) for r in c.fetchall()]
    for r in rows:
        r['valor_fmt'] = f"${abs(r['valor']):,.0f}".replace(",", ".")
    conn.close()
    return {"transacciones": rows, "total": total}

def obtener_sugerencias_cruce(tx_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, entidad, valor, fecha_date, es_ingreso, descripcion, categoria, notas FROM transacciones WHERE id=?", (tx_id,))
    src = c.fetchone()
    if not src:
        conn.close()
        return []
    src = dict(src)

    if src['entidad'] == 'myfinance':
        target = ('nequi', 'nu', 'rappicard')
    else:
        target = ('myfinance',)

    placeholders = ','.join('?' for _ in target)
    c.execute(f"""
        SELECT id, entidad, valor, fecha_date, es_ingreso, descripcion, categoria, notas
        FROM transacciones
        WHERE entidad IN ({placeholders}) AND cruzada = 0 AND es_ingreso = ?
    """, (*target, src['es_ingreso']))
    candidates = [dict(r) for r in c.fetchall()]
    conn.close()

    from datetime import date as dt_date
    src_valor = abs(src['valor'])
    src_fecha = dt_date.fromisoformat(src['fecha_date']) if src['fecha_date'] else None

    resultados = []
    for cand in candidates:
        cand_valor = abs(cand['valor'])
        cand_fecha = dt_date.fromisoformat(cand['fecha_date']) if cand['fecha_date'] else None
        max_valor = max(src_valor, cand_valor)
        diff_valor = abs(src_valor - cand_valor)
        if diff_valor > max(0.05 * max_valor, 5000):
            continue
        if src_fecha and cand_fecha:
            diff_dias = abs((src_fecha - cand_fecha).days)
            if diff_dias > 7:
                continue
            monto_score = max(0, 1 - diff_valor / max(1, max_valor))
            fecha_score = max(0, 1 - diff_dias / 7)
            score = round((monto_score * 0.6 + fecha_score * 0.4) * 100, 1)
        else:
            score = 0
            diff_dias = 999

        resultados.append({
            'id': cand['id'],
            'entidad': cand['entidad'],
            'valor': cand['valor'],
            'fecha_date': cand['fecha_date'],
            'descripcion': cand['descripcion'],
            'categoria': cand['categoria'],
            'notas': cand.get('notas', ''),
            'score': score,
            'diff_valor': round(diff_valor),
            'diff_dias': diff_dias,
        })

    resultados.sort(key=lambda x: x['score'], reverse=True)
    return resultados

def cruzar_transaccion(tx_id_bancaria, tx_id_myfinance):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT categoria, notas FROM transacciones WHERE id=?", (tx_id_myfinance,))
    myfinance = c.fetchone()
    if not myfinance:
        conn.close()
        return False
    categoria = myfinance['categoria']
    notas = myfinance['notas'] or ''
    c.execute("UPDATE transacciones SET cruzada=1 WHERE id=?", (tx_id_bancaria,))
    c.execute("UPDATE transacciones SET cruzada=1 WHERE id=?", (tx_id_myfinance,))
    if categoria:
        c.execute("UPDATE transacciones SET categoria=? WHERE id=?", (categoria, tx_id_bancaria))
    if notas:
        c.execute("UPDATE transacciones SET notas=? WHERE id=?", (notas, tx_id_bancaria))
    conn.commit()
    conn.close()
    return True

def obtener_estadisticas_cruce():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM transacciones WHERE cruzada=0")
    sin_cruzar = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM transacciones WHERE cruzada=1")
    cruzadas = c.fetchone()[0]
    c.execute("SELECT entidad, COUNT(*) as total FROM transacciones WHERE cruzada=0 GROUP BY entidad")
    por_entidad = [dict(r) for r in c.fetchall()]
    c.execute("SELECT categoria, COUNT(*) as total FROM transacciones WHERE cruzada=0 GROUP BY categoria")
    por_categoria = [dict(r) for r in c.fetchall()]
    conn.close()
    return {
        'sin_cruzar': sin_cruzar,
        'cruzadas': cruzadas,
        'por_entidad': por_entidad,
        'por_categoria': por_categoria,
    }

def obtener_resumen_anual(anio):
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT
            COUNT(*) as num_transacciones,
            COALESCE(SUM(CASE WHEN es_ingreso=1 THEN valor ELSE 0 END),0) as total_ingresos,
            COALESCE(SUM(CASE WHEN es_ingreso=0 THEN ABS(valor) ELSE 0 END),0) as total_gastos
        FROM transacciones
        WHERE strftime('%Y', fecha_date) = ?
    """, (str(anio),))
    r = dict(c.fetchone())
    conn.close()
    r["total_ingresos"] = round(r["total_ingresos"])
    r["total_gastos"] = round(r["total_gastos"])
    r["balance"] = r["total_ingresos"] - r["total_gastos"]
    r["ingreso_promedio_mensual"] = round(r["total_ingresos"] / 12) if r["total_ingresos"] > 0 else 0
    r["gasto_promedio_mensual"] = round(r["total_gastos"] / 12) if r["total_gastos"] > 0 else 0
    for k in ("total_ingresos", "total_gastos", "balance", "ingreso_promedio_mensual", "gasto_promedio_mensual"):
        v = r[k]
        r[f"{k}_fmt"] = f"${v:,}".replace(",", ".")
    return r
