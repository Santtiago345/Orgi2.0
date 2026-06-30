import sqlite3, os
from datetime import datetime, timedelta, date

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE, "outputs", "db", "finanzas_unificadas.db")
DB_COMPLETA = os.path.join(BASE, "outputs", "db", "finanzas_unificada_completa.db")

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
    c.execute("""
        INSERT INTO transacciones (fecha, fecha_date, descripcion, valor, categoria, entidad, es_ingreso, notas, metodo_pago)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (fecha, fecha, descripcion, valor, categoria, entidad, es_ingreso, notas, metodo_pago))
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
    info = {}
    for r in c.fetchall():
        info[r['tx_id']] = {
            'cuota_actual': r['cuota_actual'],
            'total_cuotas': r['total_cuotas'],
            'compra_desc': r['compra_desc'],
            'valor_total': r['valor_total'],
        }
    if own_conn:
        conn.close()
    return info

# ─── ETIQUETAS ────────────────────────────────────────────────

def obtener_etiquetas():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM etiquetas ORDER BY nombre")
    rows = [dict(r) for r in c.fetchall()]
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
    c.execute("""
        SELECT e.id, e.nombre, e.color
        FROM etiquetas e
        JOIN transaccion_etiquetas te ON te.etiqueta_id = e.id
        WHERE te.transaccion_id = ?
        ORDER BY e.nombre
    """, (transaccion_id,))
    return [dict(r) for r in c.fetchall()]

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
    """Return credit card info and credit data for the credit profile page."""
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT fuente, COUNT(*) as num_extractos,
               MAX(anio*100+mes) as ultimo_periodo,
               SUM(COALESCE(total_pagar,0)) as deuda_total,
               SUM(COALESCE(pago_minimo,0)) as pago_minimo_total,
               SUM(COALESCE(cupo_total,0)) as cupo_total,
               SUM(COALESCE(saldo_anterior,0)) as saldo_anterior,
               SUM(COALESCE(total_cargos,0)) as total_cargos,
               SUM(COALESCE(total_abonos,0)) as total_abonos
        FROM extractos
        WHERE fuente IN ('nu','rappicard')
        GROUP BY fuente
    """)
    tarjetas = [dict(r) for r in c.fetchall()]

    c.execute("""
        SELECT id, archivo, fuente, periodo, anio, mes,
               total_pagar, pago_minimo, cupo_total, saldo_anterior,
               saldo_actual, total_cargos, total_abonos,
               fecha_corte, fecha_pago, titular
        FROM extractos
        WHERE fuente IN ('nu','rappicard')
        ORDER BY anio DESC, mes DESC
    """)
    extractos_tc = [dict(r) for r in c.fetchall()]
    conn.close()

    return {
        "tarjetas": tarjetas,
        "extractos": extractos_tc,
    }

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
        SELECT id, fecha, fecha_date, descripcion, valor, categoria, entidad, es_ingreso, notas, metodo_pago
        FROM transacciones
        WHERE extracto_id=?
        ORDER BY fecha_date DESC
    """, (extracto_id,))
    txs = [dict(r) for r in c.fetchall()]
    for t in txs:
        t['tags'] = obtener_etiquetas_transaccion(conn, t['id'])

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
