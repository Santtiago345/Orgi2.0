import sqlite3
import os
from datetime import datetime

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_DIR, "data")
OUTPUT_DB = os.path.join(DATA_DIR, "final_finanzas.db")

MYFINANCE_DB = os.path.join(DATA_DIR, "myfinance", "MyFinance.db")
NEQUI_DB = os.path.join(DATA_DIR, "nequi", "nequi_finanzas.db")
NU_DB = os.path.join(DATA_DIR, "nu", "nu_finanzas.db")
RAPPI_DB = os.path.join(DATA_DIR, "rappicard", "rappicard_finanzas.db")
DALE_DB = os.path.join(DATA_DIR, "dale", "dale_finanzas.db")
DAVIPLATA_DB = os.path.join(DATA_DIR, "daviplata", "daviplata_finanzas.db")

def create_schema(cursor):
    cursor.executescript("""
        DROP TABLE IF EXISTS transacciones;
        DROP TABLE IF EXISTS compras_diferidas;
        DROP TABLE IF EXISTS cuotas_tarjeta;
        DROP TABLE IF EXISTS categorias;
        DROP TABLE IF EXISTS extractos;
        DROP TABLE IF EXISTS etiquetas;
        DROP TABLE IF EXISTS transaccion_etiquetas;
        
        CREATE TABLE categorias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE
        );
        
        CREATE TABLE extractos (
            id INTEGER PRIMARY KEY,
            archivo TEXT,
            periodo TEXT,
            anio INTEGER,
            mes INTEGER,
            titular TEXT,
            cuenta TEXT,
            saldo_anterior REAL,
            total_abonos REAL,
            total_cargos REAL,
            saldo_actual REAL,
            saldo_promedio REAL,
            intereses REAL,
            num_transacciones INTEGER,
            total_pagar REAL,
            pago_minimo REAL,
            cupo_total REAL,
            fecha_corte TEXT,
            fecha_pago TEXT,
            interes_corriente REAL,
            tasa_mensual REAL,
            tasa_anual_ea REAL,
            es_refinanciacion INTEGER DEFAULT 0,
            fuente TEXT,
            tipo TEXT
        );
        
        CREATE TABLE compras_diferidas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha DATE,
            descripcion TEXT,
            valor_total REAL,
            total_cuotas INTEGER,
            fuente TEXT,
            categoria TEXT,
            cruzada INTEGER DEFAULT 0
        );
        
        CREATE TABLE cuotas_tarjeta (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            compra_diferida_id INTEGER REFERENCES compras_diferidas(id),
            num_cuota INTEGER,
            valor_cuota REAL,
            estado_pago TEXT DEFAULT 'pendiente',
            extracto_id INTEGER REFERENCES extractos(id)
        );
        
        CREATE TABLE transacciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            fecha_date DATE,
            descripcion TEXT,
            valor REAL,
            entidad TEXT,
            cruzada INTEGER DEFAULT 0,
            categoria TEXT,
            es_ingreso INTEGER DEFAULT 0,
            notas TEXT,
            extracto_id INTEGER REFERENCES extractos(id),
            metodo_pago TEXT,
            original_id TEXT,
            banco_id INTEGER
        );
        
        CREATE TABLE etiquetas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE,
            color TEXT
        );
        
        CREATE TABLE transaccion_etiquetas (
            transaccion_id INTEGER REFERENCES transacciones(id),
            etiqueta_id INTEGER REFERENCES etiquetas(id),
            PRIMARY KEY(transaccion_id, etiqueta_id)
        );
    """)

def round_thousands(val):
    if val is None:
        return 0
    return round(val / 1000.0) * 1000

def load_myfinance(cursor_myf):
    query = """
        SELECT t.uid, t.date, t.amountInDefaultCurrency, t.type, t.comment, c.title
        FROM "transaction" t
        LEFT JOIN sync_link sl ON t.uid = sl.entityUid AND sl.entityType = 'transaction' AND sl.otherType = 'category'
        LEFT JOIN category c ON sl.otherUid = c.uid
        WHERE t.isRemoved = 0
    """
    cursor_myf.execute(query)
    rows = cursor_myf.fetchall()
    
    myf_data = []
    for r in rows:
        uid, date_str, amount, t_type, comment, cat_title = r
        if not date_str:
            continue
        try:
            fecha_date = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
            
        real_amount = (amount or 0) / 100.0
        if t_type == "Expense":
            real_amount = -abs(real_amount)
        elif t_type == "Income":
            real_amount = abs(real_amount)
            
        myf_data.append({
            "uid": uid,
            "fecha": fecha_date,
            "valor": real_amount,
            "descripcion": comment or "Transaccion MyFinance",
            "categoria": cat_title or "Sin clasificar",
            "cruzada": 0
        })
    return myf_data

def load_bank_extractos(db_path, fuente, cursor_final, id_offset):
    if not os.path.exists(db_path):
        return
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM extractos")
    rows = cursor.fetchall()
    
    tipo = "cuenta" if fuente.lower() in ("nequi", "dale", "daviplata") else "tarjeta_credito"
    
    for r in rows:
        d = dict(r)
        d['fuente'] = fuente.lower()
        d['tipo'] = tipo
        d['id'] = d['id'] + id_offset
        
        # Build dynamic insert
        cols = []
        vals = []
        for k, v in d.items():
            cols.append(k)
            vals.append(v)
            
        placeholders = ", ".join(["?"] * len(vals))
        col_names = ", ".join(cols)
        
        cursor_final.execute(f"INSERT INTO extractos ({col_names}) VALUES ({placeholders})", vals)
    conn.close()

def load_bank_db(db_path, fuente, id_offset):
    if not os.path.exists(db_path):
        return []
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM transacciones")
    rows = cursor.fetchall()
    data = []
    for r in rows:
        d = dict(r)
        fecha_str = d.get('fecha_date') or d.get('fecha')
        try:
            fecha_date = datetime.strptime(fecha_str[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue
            
        data.append({
            "banco_id": d.get('id'),
            "extracto_id": d.get('extracto_id') + id_offset if d.get('extracto_id') else None,
            "fecha": fecha_date,
            "descripcion": d.get('descripcion_normalizada') or d.get('descripcion'),
            "valor": d.get('valor'),
            "categoria": d.get('categoria'),
            "fuente": fuente,
            "cuota_actual": d.get('cuota_actual') or 1,
            "total_cuotas": d.get('total_cuotas') or 1,
            "cruzada": 0
        })
    conn.close()
    return data

def build_database():
    try:
        if os.path.exists(OUTPUT_DB):
            os.remove(OUTPUT_DB)
    except PermissionError:
        print("WARNING: No se pudo eliminar final_finanzas.db (en uso). Reconstruyendo sobre la existente.")
        pass

    conn_final = sqlite3.connect(OUTPUT_DB)
    cursor_final = conn_final.cursor()
    create_schema(cursor_final)
    
    conn_myf = sqlite3.connect(MYFINANCE_DB)
    myf_data = load_myfinance(conn_myf.cursor())
    conn_myf.close()
    
    # Offsets for extracto_id to prevent collision
    load_bank_extractos(NEQUI_DB, "Nequi", cursor_final, 0)
    load_bank_extractos(NU_DB, "Nu", cursor_final, 1000)
    load_bank_extractos(RAPPI_DB, "Rappicard", cursor_final, 2000)
    load_bank_extractos(DALE_DB, "Dale", cursor_final, 3000)
    load_bank_extractos(DAVIPLATA_DB, "Daviplata", cursor_final, 4000)
    
    bank_data = []
    bank_data.extend(load_bank_db(NEQUI_DB, "Nequi", 0))
    bank_data.extend(load_bank_db(NU_DB, "Nu", 1000))
    bank_data.extend(load_bank_db(RAPPI_DB, "Rappicard", 2000))
    bank_data.extend(load_bank_db(DALE_DB, "Dale", 3000))
    bank_data.extend(load_bank_db(DAVIPLATA_DB, "Daviplata", 4000))
    
    normal_bank_txs = []
    deferred_purchases = {}
    
    for b_tx in bank_data:
        if b_tx["total_cuotas"] > 1:
            key = (b_tx["fuente"], b_tx["fecha"], b_tx["descripcion"], b_tx["valor"], b_tx["total_cuotas"])
            if key not in deferred_purchases:
                deferred_purchases[key] = []
            deferred_purchases[key].append(b_tx)
        else:
            normal_bank_txs.append(b_tx)
            
    def try_match(b_fecha, b_valor):
        b_valor_rounded = round_thousands(b_valor)
        for i, m_tx in enumerate(myf_data):
            if m_tx["cruzada"] == 1:
                continue
            days_diff = abs((b_fecha - m_tx["fecha"]).days)
            if days_diff <= 2:
                if abs(b_valor_rounded - m_tx["valor"]) <= 1000:
                    myf_data[i]["cruzada"] = 1
                    return m_tx
        return None

    # Normal Transactions
    for b_tx in normal_bank_txs:
        matched_myf = try_match(b_tx["fecha"], b_tx["valor"])
        
        cat = matched_myf["categoria"] if matched_myf else b_tx["categoria"]
        if not cat: cat = "Sin clasificar"
        cruzada = 1 if matched_myf else 0
            
        cursor_final.execute("""
            INSERT INTO transacciones (fecha, fecha_date, descripcion, valor, entidad, cruzada, categoria, es_ingreso, extracto_id, banco_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (b_tx["fecha"].isoformat(), b_tx["fecha"], b_tx["descripcion"], b_tx["valor"], b_tx["fuente"].lower(), cruzada, cat, 1 if b_tx["valor"] > 0 else 0, b_tx["extracto_id"], b_tx["banco_id"]))

    # Deferred Purchases
    for key, cuotas in deferred_purchases.items():
        fuente, fecha, desc, valor_total, total_cuotas = key
        
        matched_myf = try_match(fecha, valor_total)
        cat = matched_myf["categoria"] if matched_myf else cuotas[0]["categoria"]
        if not cat: cat = "Sin clasificar"
        cruzada = 1 if matched_myf else 0
            
        cursor_final.execute("""
            INSERT INTO compras_diferidas (fecha, descripcion, valor_total, total_cuotas, fuente, categoria, cruzada)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (fecha, desc, valor_total, total_cuotas, fuente.lower(), cat, cruzada))
        compra_id = cursor_final.lastrowid
        
        for cuota in cuotas:
            valor_cuota = valor_total / total_cuotas
            cursor_final.execute("""
                INSERT INTO cuotas_tarjeta (compra_diferida_id, num_cuota, valor_cuota, estado_pago, extracto_id)
                VALUES (?, ?, ?, ?, ?)
            """, (compra_id, cuota["cuota_actual"], valor_cuota, 'pendiente', cuota["extracto_id"]))

    # Unmatched MyFinance
    for m_tx in myf_data:
        if m_tx["cruzada"] == 0:
            cat = m_tx["categoria"] or "Sin clasificar"
            cursor_final.execute("""
                INSERT INTO transacciones (fecha, fecha_date, descripcion, valor, entidad, cruzada, categoria, es_ingreso, original_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (m_tx["fecha"].isoformat(), m_tx["fecha"], m_tx["descripcion"], m_tx["valor"], 'myfinance', 0, cat, 1 if m_tx["valor"] > 0 else 0, m_tx["uid"]))

    # Insert Categories
    cursor_final.execute("SELECT DISTINCT categoria FROM transacciones UNION SELECT DISTINCT categoria FROM compras_diferidas")
    for (cat,) in cursor_final.fetchall():
        if cat:
            cursor_final.execute("INSERT INTO categorias (nombre) VALUES (?)", (cat,))

    conn_final.commit()
    conn_final.close()
    print("Database built successfully at data/final_finanzas.db")

if __name__ == "__main__":
    build_database()
