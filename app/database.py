import sqlite3, os, hashlib
from datetime import datetime, timedelta, date

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE, "outputs", "db", "finanzas_unificadas.db")
DB_COMPLETA = os.path.join(BASE, "outputs", "db", "finanzas_unificada_completa.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
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
    return round(ingresos - gastos, 2), round(ingresos, 2), round(gastos, 2)

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
    """Retorna (nuevo_desde, nuevo_hasta) moviendo una unidad en la direccion (-1 o 1)."""
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
        SELECT id, fecha, fecha_date, descripcion, valor, categoria, entidad, es_ingreso, notas
        FROM transacciones
        WHERE es_ingreso=? AND fecha_date >= ? AND fecha_date <= ?
        ORDER BY fecha_date DESC
    """, (es_ingreso, fecha_desde.isoformat(), fecha_hasta.isoformat()))
    rows = [dict(r) for r in c.fetchall()]
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

def agregar_transaccion(fecha, descripcion, valor, categoria, tipo, notas="", entidad="manual"):
    es_ingreso = 1 if tipo == "ingreso" else 0
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO transacciones (fecha, fecha_date, descripcion, valor, categoria, entidad, es_ingreso, notas)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (fecha, fecha, descripcion, valor, categoria, entidad, es_ingreso, notas))
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
    """Verifica si un archivo PDF ya existe en extractos (por nombre)."""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM extractos WHERE archivo LIKE ?", (f"%{archivo_nombre}%",))
    count = c.fetchone()[0]
    conn.close()
    return count > 0
