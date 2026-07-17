"""
Comprehensive TC PDF re-parser.
- Deletes all existing Nu/RappiCard transactions from finanzas_unificadas.db
- Re-parses all PDFs with complete info: cuotas, abonos, saldos, intereses, corte
- Creates compras_tc (master purchases) and cuotas_tc (per-month cuota records)
- Populates extractos with saldo_anterior, saldo_actual, total_cargos, total_abonos, mes, fecha_corte, fecha_pago
- Abonos become income transactions (Abono TC)
- Each cuota shows capital_facturado (monthly payment) not total value
"""
import re, os, sys, sqlite3
from datetime import datetime
import pdfplumber

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE, "data")
DB_PATH = os.path.join(BASE, "outputs", "db", "finanzas_unificadas.db")

PASSWORD = "REDACTED_PWD"

# ─── HELPERS ────────────────────────────────────────────────────

def limp(val):
    """Parse '$1.234.567,89' or '1234.56' to float."""
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    val = val.strip().replace('$', '').replace(' ', '')
    if ',' in val and '.' in val:
        # Colombian format: 1.234.567,89
        val = val.replace('.', '').replace(',', '.')
    elif ',' in val:
        val = val.replace(',', '.')
    return float(val) if val else 0.0

def parse_date_nu(day, month_name, year=None):
    months = {'ENE':1,'FEB':2,'MAR':3,'ABR':4,'MAY':5,'JUN':6,'JUL':7,'AGO':8,'SEP':9,'OCT':10,'NOV':11,'DIC':12,
              'JANUARY':1,'FEBRUARY':2,'MARCH':3,'APRIL':4,'MAY':5,'JUNE':6,'JULY':7,'AUGUST':8,'SEPTEMBER':9,'OCTOBER':10,'NOVEMBER':11,'DECEMBER':12}
    m = months.get(month_name.upper()[:3], 1)
    day = int(day)
    if year is None:
        year = 2026
    else:
        year = int(year)
    return f"{year:04d}-{m:02d}-{day:02d}"

def parse_date_rappicard(date_str):
    """From '2025-10-04' to ISO."""
    return date_str.strip()

def mes_from_date(iso_date):
    if not iso_date:
        return None, None
    parts = iso_date.split('-')
    return int(parts[0]), int(parts[1])

# ─── NU PARSER ──────────────────────────────────────────────────

def parse_nu(pdf_path):
    """Return dict with header info + transactions list."""
    result = {
        'archivo': os.path.basename(pdf_path),
        'fuente': 'nu',
        'tipo': 'tarjeta_credito',
        'total_pagar': 0, 'pago_minimo': 0, 'cupo_total': 0,
        'cupo_usado': 0, 'cupo_disponible': 0,
        'saldo_anterior': None, 'saldo_actual': None,
        'total_cargos': 0, 'total_abonos': 0,
        'intereses': 0, 'cuota_manejo': 0, 'comisiones': 0,
        'fecha_corte': None, 'fecha_pago': None,
        'periodo': None,
        'transacciones': [],  # each: {fecha, descripcion, valor, cuota_actual, total_cuotas, capital_facturado, intereses, total_pagar_mes, restante}
        'abonos': [],
    }
    try:
        with pdfplumber.open(pdf_path, password=PASSWORD) as pdf:
            full_text = ""
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    full_text += t + "\n"
    except:
        with pdfplumber.open(pdf_path) as pdf:
            full_text = ""
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    full_text += t + "\n"

    text = full_text

    # --- Header ---
    # Nu: labels on one line, dates on next: "Fecha l�mite de pago Fecha de corte Periodo facturado\n10 JUN 2026 21 MAY 2026 09 MAY - 20 MAY 2026"
    # Capture the date line directly
    m = re.search(r'(\d{1,2})\s+(\w+)\s+(\d{4})\s+(\d{1,2})\s+(\w+)\s+(\d{4})\s+(\d{1,2})\s+(\w+)\s*-\s*(\d{1,2})\s+(\w+)\s+(\d{4})', text)
    if m:
        result['fecha_pago'] = parse_date_nu(m.group(1), m.group(2), m.group(3))
        result['fecha_corte'] = parse_date_nu(m.group(4), m.group(5), m.group(6))
        d1 = parse_date_nu(m.group(7), m.group(8), m.group(11))
        d2 = parse_date_nu(m.group(9), m.group(10), m.group(11))
        result['periodo'], result['periodo_desde'], result['periodo_hasta'] = f"{d1} a {d2}", d1, d2
    else:
        # Fallback: search for individual patterns
        for pat in [
            r'Fecha l.mite de pago.*?(\d{1,2})\s+(\w+)\s+(\d{4})',
            r'(\d{1,2})\s+(\w+)\s+(\d{4}).*?Fecha l.mite de pago',
        ]:
            m = re.search(pat, text, re.IGNORECASE | re.DOTALL)
            if m:
                result['fecha_pago'] = parse_date_nu(m.group(1), m.group(2), m.group(3))
                break
        for pat in [
            r'Fecha de corte.*?(\d{1,2})\s+(\w+)\s+(\d{4})',
            r'(\d{1,2})\s+(\w+)\s+(\d{4}).*?Fecha de corte',
        ]:
            m = re.search(pat, text, re.IGNORECASE | re.DOTALL)
            if m:
                result['fecha_corte'] = parse_date_nu(m.group(1), m.group(2), m.group(3))
                break
        m = re.search(r'Periodo facturado\s+(\d{1,2})\s+(\w+)\s+-\s+(\d{1,2})\s+(\w+)\s+(\d{4})', text, re.IGNORECASE)
        if m:
            d1 = parse_date_nu(m.group(1), m.group(2), m.group(5))
            d2 = parse_date_nu(m.group(3), m.group(4), m.group(5))
            result['periodo'] = f"{d1} a {d2}"

    # --- Resumen ---
    m = re.search(r'Deuda a pagar este mes\s+\$?([\d.,]+)', text)
    if m:
        result['total_pagar'] = limp(m.group(1))

    # "Tu cupo definido\nIntereses + $0,00\n$1.000.000,00" -> skip the Intereses line to get the actual cupo
    m = re.search(r'Tu cupo definido.*?Intereses.*?\n\$?([\d.,]+)', text, re.DOTALL)
    if not m:
        m = re.search(r'Tu cupo definido.*?\n\$?([\d.,]+)', text, re.DOTALL)
    if m:
        result['cupo_total'] = limp(m.group(1))

    m = re.search(r'Usado.*?\$?([\d.,]+).*?Disponible.*?\$?([\d.,]+)', text, re.DOTALL)
    if m:
        result['cupo_usado'] = limp(m.group(1))
        result['cupo_disponible'] = limp(m.group(2))
    else:
        m = re.search(r'Usado.*?\$?([\d.,]+)', text, re.DOTALL)
        if m:
            result['cupo_usado'] = limp(m.group(1))
        m = re.search(r'Disponible.*?\$?([\d.,]+)', text, re.DOTALL)
        if m:
            result['cupo_disponible'] = limp(m.group(1))

    m = re.search(r'Intereses\s+\+?\s*\$?([\d.,]+)', text)
    if m:
        result['intereses'] = limp(m.group(1))

    m = re.search(r'Cuota de manejo\s+\+?\s*\$?([\d.,]+)', text)
    if m:
        result['cuota_manejo'] = limp(m.group(1))

    # Abonos (payments made)
    m = re.search(r'Abonaste\s+\$?([\d.,]+)', text)
    if m:
        abono = limp(m.group(1))
        result['total_abonos'] = abono
        result['abonos'].append({'fecha': result.get('fecha_pago', ''), 'valor': abono, 'descripcion': 'PAGO ABONO NU'})

    # PAGO MÍNIMO
    m = re.search(r'PAGO M.NIMO\s+\$?([\d.,]+)', text)
    if m:
        result['pago_minimo'] = limp(m.group(1))

    # Deuda restante
    m = re.search(r'Deuda restante\s+\+?\s*\$?([\d.,]+)', text)
    restante = limp(m.group(1)) if m else 0

    # PAGO HASTA EL
    m = re.search(r'PAGO HASTA EL\s+[\d\s\w]+\$?([\d.,]+)', text)
    if m:
        pago_total = limp(m.group(1))
        if pago_total > result['total_pagar']:
            result['total_pagar'] = pago_total

    # --- Total cargos ---
    result['total_cargos'] = result['total_pagar'] + result['intereses'] + result.get('cuota_manejo', 0)

    # --- Transactions ---
    tx_pattern = re.compile(
        r'(\d{2})\s+(\w+)\s+(.+?)\s+\$?([\d.,]+)\s+(\d+)\s+de\s+(\d+)\s+\$?([\d.,]+)'
    )
    for m in tx_pattern.finditer(text):
        day = m.group(1)
        month_name = m.group(2)
        desc = m.group(3).strip()
        valor = limp(m.group(4))
        cuota_actual = int(m.group(5))
        total_cuotas = int(m.group(6))
        total_pagar_mes = limp(m.group(7))

        # Build date
        if result.get('fecha_corte'):
            year = result['fecha_corte'][:4]
        else:
            year = '2026'
        fecha = parse_date_nu(day, month_name, year)

        tx = {
            'fecha': fecha,
            'descripcion': desc,
            'valor': valor,
            'capital_facturado': total_pagar_mes if total_cuotas > 1 else valor,
            'cuota_actual': cuota_actual,
            'total_cuotas': total_cuotas,
            'intereses': 0,
            'total_pagar_mes': total_pagar_mes,
            'restante': 0,
        }
        result['transacciones'].append(tx)

    return result


# ─── RAPPICARD PARSER ─────────────────────────────────────────

def parse_rappicard(pdf_path):
    """Return dict with header info + transactions list."""
    result = {
        'archivo': os.path.basename(pdf_path),
        'fuente': 'rappicard',
        'tipo': 'tarjeta_credito',
        'total_pagar': 0, 'pago_minimo': 0, 'pago_alternativo': None,
        'cupo_total': 0, 'cupo_utilizado': 0,
        'saldo_anterior': 0, 'saldo_actual': None,
        'total_cargos': 0, 'total_abonos': 0,
        'intereses': 0,
        'fecha_corte': None, 'fecha_pago': None,
        'periodo': None, 'periodo_desde': None, 'periodo_hasta': None,
        'cashback': 0,
        'transacciones': [],  # each: {fecha, descripcion, valor, capital_facturado, cuota_actual, total_cuotas, capital_pendiente, tasa_mv, tasa_ea}
        'abonos': [],
    }
    try:
        with pdfplumber.open(pdf_path, password=PASSWORD) as pdf:
            full_text = ""
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    full_text += t + "\n"
    except:
        with pdfplumber.open(pdf_path) as pdf:
            full_text = ""
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    full_text += t + "\n"

    text = full_text

    # --- Header ---
    m = re.search(r'Cupo utilizado\s+\$?([\d.,]+)', text)
    if m:
        result['cupo_utilizado'] = limp(m.group(1))

    m = re.search(r'Pago m.nimo\s+\$?([\d.,]+)', text)
    if m:
        result['pago_minimo'] = limp(m.group(1))

    m = re.search(r'Pago alternativo\*?\s+\$?([\d.,]+)', text)
    if m:
        result['pago_alternativo'] = limp(m.group(1))

    # RappiCard: dates appear as three consecutive lines after the header:
    #   10 nov 2025       <- fecha de pago
    #   Desde 30 sep 2025  <- periodo_desde
    #   Hasta 30 oct 2025  <- periodo_hasta
    # Capture via the date-only line pattern
    m = re.search(r'^(?:(\d{1,2})\s+(\w+)\s+(\d{4}))\s*$', text, re.MULTILINE)
    if m:
        result['fecha_pago'] = parse_date_nu(m.group(1), m.group(2), m.group(3))
    else:
        # fallback: try loose pattern near "Fecha de pago"
        for pat in [
            r'Fecha de pago[\s\S]*?(\d{1,2})\s+(\w+)\s+(\d{4})',
            r'(\d{1,2})\s+(\w+)\s+(\d{4})[\s\S]*?Fecha de pago',
        ]:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                if m.group(1).isdigit() and len(m.group(1)) <= 2:
                    result['fecha_pago'] = parse_date_nu(m.group(1), m.group(2), m.group(3))
                break

    # Periodo
    m = re.search(r'Desde\s+(\d{1,2})\s+(\w+)\s+(\d{4})', text, re.IGNORECASE)
    if m:
        result['periodo_desde'] = parse_date_nu(m.group(1), m.group(2), m.group(3))

    m = re.search(r'Hasta\s+(\d{1,2})\s+(\w+)\s+(\d{4})', text, re.IGNORECASE)
    if m:
        result['periodo_hasta'] = parse_date_nu(m.group(1), m.group(2), m.group(3))

    if result['periodo_desde'] and result['periodo_hasta']:
        result['periodo'] = f"{result['periodo_desde']} a {result['periodo_hasta']}"
        if not result.get('fecha_corte'):
            result['fecha_corte'] = result['periodo_hasta']

    m = re.search(r'Pago total\s+\$?([\d.,]+)', text)
    if m:
        result['total_pagar'] = limp(m.group(1))

    m = re.search(r'Cupo total:?\s*\$?([\d.,]+)', text)
    if m:
        result['cupo_total'] = limp(m.group(1))

    m = re.search(r'Saldo anterior\s+\$?([\d.,]+)', text)
    if m:
        result['saldo_anterior'] = limp(m.group(1))

    m = re.search(r'Saldo periodo anterior\s+\$?([\d.,]+)', text)
    if m:
        result['saldo_anterior'] = limp(m.group(1))

    m = re.search(r'Saldo disponible\s+\$?([\d.,]+)', text)
    if m:
        result['saldo_actual'] = limp(m.group(1))

    # Total cargos = total_pagar + intereses (from breakdown)
    # Find "Intereses corrientes" lines
    intereses_matches = re.findall(r'Intereses corrientes\s+\$?([\d.,]+)', text)
    for val in intereses_matches:
        result['intereses'] += limp(val)

    # Cashback
    m = re.search(r'Cashback mes\s+\$?([\d.,]+)', text)
    if m:
        result['cashback'] = limp(m.group(1))

    # Find pagos (abonos) in text
    # Look for "Pagos (incluye abonos y cancelaciones)" 
    m = re.search(    r'-?\s*Pagos\s*\(incluye abonos y cancelaciones\)\s*\-?\$?(-?[\d.,]+)', text)
    if m:
        result['total_abonos'] = abs(limp(m.group(1)))

    # --- Transactions ---
    # Pattern 1: Rows with cuotas (X de Y)
    tx_pattern = re.compile(
        r'(Virtual|Fisica|F[íi]sica|-)\s+(\d{4}-\d{2}-\d{2})\s+(.+?)\s+\$?(-?[\d.,]+)\s+\$?(-?[\d.,]+)\s+(\d+)\s+de\s+(\d+)'
    )
    # Pattern 2: Rows without cuotas (payments/abonos/dev for single-pay)
    abono_pattern = re.compile(
        r'-\s+(\d{4}-\d{2}-\d{2})\s+(PAGOS POR[^$]+?|DEVOLUCION[^$]+?|ABONO[^$]+?)\s+\$?(-?[\d.,]+)'
    )

    for m in tx_pattern.finditer(text):
        card_type = m.group(1)
        fecha = m.group(2)
        desc = m.group(3).strip()
        valor = limp(m.group(4))
        capital_facturado = limp(m.group(5))
        cuota_actual = int(m.group(6))
        total_cuotas = int(m.group(7))

        upper_desc = desc.upper()
        if any(w in upper_desc for w in ['PAGOS POR', 'PAGOS RAPPIPAY', 'PAGOS*', 'ABONO A', 'PAGO DIRECTO']) or (upper_desc.startswith('PAGOS') and 'POR' in upper_desc):
            result['abonos'].append({
                'fecha': fecha, 'descripcion': desc,
                'valor': abs(valor),
                'capital_facturado': abs(capital_facturado) if capital_facturado else abs(valor),
            })
            continue

        tx = {
            'fecha': fecha, 'descripcion': desc, 'valor': valor,
            'capital_facturado': capital_facturado if capital_facturado else valor,
            'cuota_actual': cuota_actual, 'total_cuotas': total_cuotas,
            'capital_pendiente': 0, 'tasa_mv': 0, 'tasa_ea': 0,
        }
        result['transacciones'].append(tx)

    # Also capture abonos from separate pattern
    for m in abono_pattern.finditer(text):
        fecha = m.group(1)
        desc = m.group(2).strip()
        valor = limp(m.group(3))
        # Avoid duplicating if already captured by tx_pattern
        existing = any(a['fecha'] == fecha and a['valor'] == abs(valor) for a in result['abonos'])
        if not existing:
            result['abonos'].append({
                'fecha': fecha, 'descripcion': desc,
                'valor': abs(valor),
                'capital_facturado': abs(valor),
            })

    # Calculate total_cargos from transactions sum
    total_tx = sum(t['capital_facturado'] for t in result['transacciones'])
    total_abonos = sum(a['valor'] for a in result['abonos'])
    if result['total_abonos'] == 0 and total_abonos > 0:
        result['total_abonos'] = total_abonos
    # total_cargos = sum of this month's charges (capital_facturado + intereses)
    result['total_cargos'] = total_tx + result['intereses']

    return result


# ─── DB OPERATIONS ──────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def ensure_tables(conn):
    c = conn.cursor()
    c.execute("DROP TABLE IF EXISTS compras_tc")
    c.execute("DROP TABLE IF EXISTS cuotas_tc")
    c.execute("""
        CREATE TABLE compras_tc (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entidad TEXT NOT NULL,
            descripcion TEXT NOT NULL,
            valor_total REAL NOT NULL,
            fecha_compra TEXT,
            total_cuotas INTEGER DEFAULT 1,
            cuotas_pagadas INTEGER DEFAULT 0,
            tasa_interes_mv REAL,
            tasa_interes_ea REAL,
            estado TEXT DEFAULT 'en_curso',
            created_at TEXT DEFAULT (date('now'))
        )
    """)
    c.execute("""
        CREATE TABLE cuotas_tc (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            compra_id INTEGER REFERENCES compras_tc(id) ON DELETE CASCADE,
            extracto_id INTEGER REFERENCES extractos(id),
            cuota_numero INTEGER,
            capital_facturado REAL,
            capital_pendiente REAL,
            intereses REAL DEFAULT 0,
            fecha TEXT,
            UNIQUE(compra_id, extracto_id)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS cuotas_tc (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            compra_id INTEGER REFERENCES compras_tc(id) ON DELETE CASCADE,
            extracto_id INTEGER REFERENCES extractos(id),
            cuota_numero INTEGER,
            capital_facturado REAL,
            capital_pendiente REAL,
            intereses REAL DEFAULT 0,
            fecha TEXT,
            UNIQUE(compra_id, extracto_id)
        )
    """)
    conn.commit()

def clear_tc_data(conn):
    """Delete ALL Nu/RappiCard transactions and reset extracto fields."""
    c = conn.cursor()
    c.execute("DELETE FROM cuotas_tc")
    c.execute("DELETE FROM compras_tc")
    c.execute("DELETE FROM transaccion_etiquetas WHERE transaccion_id IN (SELECT id FROM transacciones WHERE entidad IN ('nu','rappicard'))")
    c.execute("DELETE FROM transacciones WHERE entidad IN ('nu','rappicard')")
    # Reset extracto fields for TC extractos
    c.execute("""
        UPDATE extractos SET 
            saldo_anterior=NULL, saldo_actual=NULL, 
            total_cargos=NULL, total_abonos=NULL,
            pago_minimo=NULL, total_pagar=NULL,
            fecha_corte=NULL, fecha_pago=NULL,
            mes=NULL
        WHERE fuente IN ('nu','rappicard')
    """)
    conn.commit()
    print(f"  Deleted existing TC transactions")

def upsert_extracto(conn, data):
    """Update or insert an extracto record."""
    c = conn.cursor()
    archivo = data['archivo']
    
    # Find existing
    c.execute("SELECT id FROM extractos WHERE archivo LIKE ?", (f"%{archivo}%",))
    row = c.fetchone()
    
    if row:
        eid = row['id']
        c.execute("""
            UPDATE extractos SET
                total_pagar=?, pago_minimo=?, cupo_total=?,
                saldo_anterior=?, total_cargos=?, total_abonos=?,
                saldo_actual=?,
                fecha_corte=?, fecha_pago=?, periodo=?,
                mes=?, anio=?
            WHERE id=?
        """, (
            data.get('total_pagar'), data.get('pago_minimo'), data.get('cupo_total'),
            data.get('saldo_anterior'), data.get('total_cargos'), data.get('total_abonos', 0),
            data.get('cupo_utilizado'),
            data.get('fecha_corte'), data.get('fecha_pago'), data.get('periodo'),
            data.get('mes'), data.get('anio'),
            eid
        ))
    else:
        c.execute("""
            INSERT INTO extractos (archivo, fuente, tipo, periodo, anio, mes,
                titular, total_pagar, pago_minimo, cupo_total,
                saldo_anterior, total_cargos, total_abonos, saldo_actual,
                fecha_corte, fecha_pago, num_transacciones)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            archivo, data['fuente'], 'tarjeta_credito', data.get('periodo'),
            data.get('anio'), data.get('mes'),
            'JOEL SANTIAGO NEUTA JASPE',
            data.get('total_pagar'), data.get('pago_minimo'), data.get('cupo_total'),
            data.get('saldo_anterior'), data.get('total_cargos'), data.get('total_abonos', 0),
            data.get('cupo_utilizado'),
            data.get('fecha_corte'), data.get('fecha_pago'),
            len(data.get('transacciones', []))
        ))
        eid = c.lastrowid
    
    c.execute("UPDATE extractos SET num_transacciones=? WHERE id=?",
              (len(data.get('transacciones', [])), eid))
    conn.commit()
    return eid

def update_num_transacciones(conn, eid, n):
    conn.execute("UPDATE extractos SET num_transacciones=? WHERE id=?", (n, eid))
    conn.commit()

from utils.normalize import normalize_valor


def insert_transaccion(conn, extracto_id, fecha, descripcion, valor, categoria, entidad, es_ingreso, metodo_pago, notas=""):
    """Inserta transacción normalizando signo: ingresos positivos, gastos negativos."""
    c = conn.cursor()
    v = normalize_valor(valor, es_ingreso=es_ingreso)
    c.execute("""
        INSERT INTO transacciones (extracto_id, fecha, fecha_date, descripcion, valor, entidad, categoria, es_ingreso, metodo_pago, notas)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (extracto_id, fecha, fecha, descripcion, v, entidad, categoria, es_ingreso, metodo_pago, notas))
    conn.commit()
    return c.lastrowid

def find_or_create_compra(conn, entidad, descripcion, valor_total, fecha_compra, total_cuotas, tasa_mv=0, tasa_ea=0):
    """Find existing compra_tc or create new one. Return compra_id."""
    c = conn.cursor()
    c.execute("""
        SELECT id, total_cuotas, cuotas_pagadas FROM compras_tc
        WHERE entidad=? AND descripcion=? AND ABS(valor_total - ?) < 1
    """, (entidad, descripcion.strip().upper(), valor_total))
    row = c.fetchone()
    if row:
        return row['id'], row['total_cuotas']
    
    c.execute("""
        INSERT INTO compras_tc (entidad, descripcion, valor_total, fecha_compra, total_cuotas, tasa_interes_mv, tasa_interes_ea)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (entidad, descripcion.strip().upper(), valor_total, fecha_compra, total_cuotas, tasa_mv, tasa_ea))
    conn.commit()
    return c.lastrowid, total_cuotas

def insert_cuota(conn, compra_id, extracto_id, cuota_numero, capital_facturado, capital_pendiente, intereses, fecha):
    c = conn.cursor()
    c.execute("""
        INSERT OR REPLACE INTO cuotas_tc (compra_id, extracto_id, cuota_numero, capital_facturado, capital_pendiente, intereses, fecha)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (compra_id, extracto_id, cuota_numero, capital_facturado, capital_pendiente, intereses, fecha))
    conn.commit()

def update_compra_estado(conn):
    """Update estado and cuotas_pagadas for all compras_tc."""
    c = conn.cursor()
    c.execute("""
        SELECT compra_id, COUNT(*) as num_pagadas, MAX(cuota_numero) as max_cuota
        FROM cuotas_tc GROUP BY compra_id
    """)
    for row in c.fetchall():
        c2 = conn.cursor()
        c2.execute("SELECT total_cuotas FROM compras_tc WHERE id=?", (row['compra_id'],))
        compra = c2.fetchone()
        if not compra:
            continue
        total = max(compra['total_cuotas'], row['num_pagadas'])
        pagadas = row['num_pagadas']
        estado = 'pagada' if pagadas >= total else 'en_curso'
        c2.execute("UPDATE compras_tc SET estado=?, cuotas_pagadas=? WHERE id=?",
                   (estado, pagadas, row['compra_id']))
    conn.commit()


# ─── MAIN REPARSE ────────────────────────────────────────────────

BANCO_PDFS = {
    'nu': ['nu_2026-05_tarjeta_credito.pdf', 'nu_2026-06_tarjeta_credito.pdf'],
    'rappicard': [
        'rappicard_2025-09_tarjeta_credito.pdf',
        'rappicard_2025-10_tarjeta_credito.pdf',
        'rappicard_2025-11_tarjeta_credito.pdf',
        'rappicard_2025-12_tarjeta_credito.pdf',
        'rappicard_2026-01_tarjeta_credito.pdf',
        'rappicard_2026-02_tarjeta_credito.pdf',
        'rappicard_2026-03_tarjeta_credito.pdf',
        'rappicard_2026-04_tarjeta_credito.pdf',
    ],
}

# Category classification for TC purchases
def clasificar_tc(desc):
    desc_upper = desc.upper()
    if any(w in desc_upper for w in ['RAPPI', 'DOMINOS', 'SANDWICH', 'DUNKIN', 'PANADERIA', 'PANADERIA']):
        return 'Comida'
    if any(w in desc_upper for w in ['EXITO', 'TIENDAS', 'DOLLARCITY', 'C C ', 'OXXO']):
        return 'Compras general'
    if any(w in desc_upper for w in ['BOLD*CELULAR', 'BOLD*THE ROSE', 'BOLD*DOCE']):
        return 'Tecnologia'
    if any(w in desc_upper for w in ['TUBOLETA', 'TU BOLETA', 'BOLETA', 'BOLE']):
        return 'Entretenimiento'
    if any(w in desc_upper for w in ['MOTEL']):
        return 'Varios'
    if any(w in desc_upper for w in ['DA QUEI', 'LA NACIONAL DE LICORES', 'LICORES']):
        return 'Entretenimiento'
    if any(w in desc_upper for w in ['CARULLA', 'JERONIMO', 'ESPACIO NATURA', 'MINISO', 'TRENDY']):
        return 'Compras general'
    if any(w in desc_upper for w in ['ESTACION PRIMAX', 'GASOLINA', 'COMBUSTIBLE']):
        return 'Transporte'
    if any(w in desc_upper for w in ['CAC*DROGUERIA', 'DROGUERIA']):
        return 'Salud'
    if any(w in desc_upper for w in ['COMCEL', 'UNE TELCO', 'GOOGLE']):
        return 'Servicios'
    if any(w in desc_upper for w in ['INVERSIONES', 'CASAMILAS', 'LA CHINGONA']):
        return 'Compras general'
    if any(w in desc_upper for w in ['BOLD*CELULARESNI', 'BOLDT*CEL']):
        return 'Tecnologia'
    if any(w in desc_upper for w in ['PANAMERICANA']):
        return 'Educacion'
    if any(w in desc_upper for w in ['PWSCCO']):
        return 'Comida'
    return 'Sin clasificar'


def reparse_all():
    print("=" * 60)
    print("REPARSING TC EXTRACTOS (Nu + RappiCard)")
    print("=" * 60)
    
    conn = get_db()
    ensure_tables(conn)
    
    # Step 1: Clear existing TC data
    print("\n[1] Clearing existing TC data...")
    clear_tc_data(conn)
    
    all_tx_count = 0
    all_abono_count = 0
    extracto_count = 0
    
    for banco, pdfs in BANCO_PDFS.items():
        print(f"\n[2] Processing {banco.upper()} ({len(pdfs)} PDFs)...")
        banco_dir = os.path.join(DATA_DIR, banco)
        
        for fname in pdfs:
            fpath = os.path.join(banco_dir, fname)
            if not os.path.exists(fpath):
                print(f"  WARNING: {fname} not found, skipping")
                continue
            
            # Parse
            if banco == 'nu':
                data = parse_nu(fpath)
            else:
                data = parse_rappicard(fpath)
            
            # Derive anio/mes from periodo or filename
            # Try to extract from filename: banco_YYYY-MM_tarjeta_credito.pdf
            fm = re.search(r'(\d{4})-(\d{2})', fname)
            if fm:
                data['anio'] = int(fm.group(1))
                data['mes'] = int(fm.group(2))
            else:
                data['anio'] = 2026
                data['mes'] = 1
            
            # Upsert extracto
            eid = upsert_extracto(conn, data)
            
            # Process transactions
            compra_map = {}  # desc_upper -> compra_id
            tx_inserted = 0
            
            for tx in data['transacciones']:
                cat = clasificar_tc(tx['descripcion'])
                # Use capital_facturado as the monthly value (the actual payment this month)
                monthly_val = -abs(tx['capital_facturado'])
                
                tid = insert_transaccion(
                    conn, eid, tx['fecha'], tx['descripcion'],
                    monthly_val, cat, banco, 0, 'tarjeta_credito'
                )
                
                # Track compra/cuota
                compra_key = tx['descripcion'].strip().upper()
                if banco == 'rappicard':
                    # For RappiCard, the total_cuotas is in the tx data
                    total_cuotas = tx['total_cuotas']
                    # Find or create compra matching by description + valor_total
                    compra_id, _ = find_or_create_compra(
                        conn, banco, compra_key, tx['valor'],
                        tx['fecha'], total_cuotas, tx.get('tasa_mv', 0), tx.get('tasa_ea', 0)
                    )
                else:
                    # For Nu
                    total_cuotas = tx['total_cuotas']
                    compra_id, _ = find_or_create_compra(
                        conn, banco, compra_key, tx['valor'],
                        tx['fecha'], total_cuotas
                    )
                
                # Insert cuota record
                insert_cuota(
                    conn, compra_id, eid, tx['cuota_actual'],
                    monthly_val, -tx.get('capital_pendiente', 0) if 'capital_pendiente' in tx else 0,
                    tx.get('intereses', 0), tx['fecha']
                )
                tx_inserted += 1
            
            # Process abonos as income transactions
            abono_inserted = 0
            for ab in data['abonos']:
                tid = insert_transaccion(
                    conn, eid, ab['fecha'], ab['descripcion'],
                    abs(ab['valor']), 'Abono TC', banco, 1, 'transferencia',
                    notas='Abono a tarjeta de credito'
                )
                abono_inserted += 1
            
            all_tx_count += tx_inserted
            all_abono_count += abono_inserted
            extracto_count += 1
            
            update_num_transacciones(conn, eid, tx_inserted)
            print(f"  {fname}: {tx_inserted} transacciones, {abono_inserted} abonos")
    
    # Update compra estados
    update_compra_estado(conn)
    
    conn.close()
    print(f"\n[3] Done! Processed {extracto_count} extractos")
    print(f"  {all_tx_count} transactions inserted")
    print(f"  {all_abono_count} abonos inserted")
    
    # Verify
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM transacciones WHERE entidad IN ('nu','rappicard')")
    total_tx = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM compras_tc")
    total_compras = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM cuotas_tc")
    total_cuotas_rec = c.fetchone()[0]
    c.execute("SELECT entidad, COUNT(*) FROM transacciones WHERE entidad IN ('nu','rappicard') GROUP BY entidad")
    per_bank = c.fetchall()
    print(f"\n  Total transactions: {total_tx} ({', '.join(f'{r[0]}: {r[1]}' for r in per_bank)})")
    print(f"  Total compras_tc: {total_compras}")
    print(f"  Total cuotas_tc: {total_cuotas_rec}")
    
    # Show extracto stats
    c.execute("SELECT id, archivo, total_pagar, pago_minimo, total_cargos, total_abonos, saldo_anterior, fecha_corte, fecha_pago FROM extractos WHERE fuente='rappicard' ORDER BY anio, mes")
    print("\n  RappiCard extractos after reparse:")
    for r in c.fetchall():
        print(f"    ID={r['id']}: {r['archivo'][:30]:30s} pagar={r['total_pagar']:>8.0f} min={r['pago_minimo']:>8.0f} cargos={r['total_cargos']:>8.0f} abonos={r['total_abonos']:>8.0f} s_ant={r['saldo_anterior']:>8.0f} corte={r['fecha_corte']} pago={r['fecha_pago']}")
    c.execute("SELECT id, archivo, total_pagar, pago_minimo, total_cargos, total_abonos, fecha_corte, fecha_pago FROM extractos WHERE fuente='nu' ORDER BY anio, mes")
    print("\n  Nu extractos after reparse:")
    for r in c.fetchall():
        print(f"    ID={r['id']}: {r['archivo'][:30]:30s} pagar={r['total_pagar']:>8.0f} min={r['pago_minimo']:>8.0f} cargos={r['total_cargos']:>8.0f} abonos={r['total_abonos']:>8.0f} corte={r['fecha_corte']} pago={r['fecha_pago']}")
    conn.close()


if __name__ == '__main__':
    reparse_all()
