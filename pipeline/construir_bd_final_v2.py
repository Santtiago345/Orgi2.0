"""
CONSTRUIR BD DEFINITIVA v2
==========================
- Carga BD antigua (divide /100)
- Carga PDFs con fechas normalizadas
- Aplica reglas de matching confirmadas por el usuario
- Clasifica correctamente gastos en efectivo
- Genera BD final SQLite + JSON + CSV + TXT
"""

import sqlite3, os, re, json, csv
from datetime import datetime, timedelta
from collections import defaultdict
from utils.normalize import normalize_valor

BASE = r"C:\Users\Santt\OneDrive\Documentos\Proyectos\Orgi2.0"
OLD_DB = os.path.join(BASE, "data", "myfinance", "MyFinance.db")
PDF_DB = os.path.join(BASE, "outputs", "db", "finanzas_unificadas.db")
OUT_DB = os.path.join(BASE, "outputs", "db", "finanzas_definitiva_v2.db")
OUT_JSON = os.path.join(BASE, "outputs", "db", "finanzas_definitiva_v2.json")
OUT_CSV = os.path.join(BASE, "outputs", "reports", "finanzas_definitiva_v2.csv")
OUT_TXT = os.path.join(BASE, "outputs", "reports", "reporte_definitivo_v2.txt")

MESES = {"ENE":1,"FEB":2,"MAR":3,"ABR":4,"MAY":5,"JUN":6,"JUL":7,"AGO":8,"SEP":9,"OCT":10,"NOV":11,"DIC":12,
         "ENERO":1,"FEBRERO":2,"MARZO":3,"ABRIL":4,"MAYO":5,"JUNIO":6,"JULIO":7,"AGOSTO":8,"SEPTIEMBRE":9,"OCTUBRE":10,"NOVIEMBRE":11,"DICIEMBRE":12}

# ============================================================
# HELPERS
# ============================================================
def normalizar_fecha(s):
    """Convierte cualquier formato de fecha a YYYY-MM-DD"""
    if not s: return None
    s = s.strip()
    # YYYY-MM-DD
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s): return s
    # DD/MM/YYYY
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", s)
    if m: return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    # DD-MM-YYYY
    m = re.match(r"^(\d{2})-(\d{2})-(\d{4})$", s)
    if m: return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    # YYYY/MM/DD
    m = re.match(r"^(\d{4})/(\d{2})/(\d{2})$", s)
    if m: return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    # DD MMM YYYY (Spanish)
    m = re.match(r"^(\d{1,2})\s+(\w+)\s+(\d{4})$", s)
    if m:
        mon = MESES.get(m.group(2).upper()[:3])
        if mon: return f"{m.group(3)}-{mon:02d}-{int(m.group(1)):02d}"
    return s

def fecha_diff(f1, f2):
    """Diferencia en dias entre dos fechas YYYY-MM-DD"""
    try:
        d1 = datetime.strptime(f1, "%Y-%m-%d") if len(f1) == 10 else datetime.strptime(f1[:10], "%Y-%m-%d")
        d2 = datetime.strptime(f2, "%Y-%m-%d") if len(f2) == 10 else datetime.strptime(f2[:10], "%Y-%m-%d")
        return abs((d1 - d2).days)
    except: return 999

def monto_cercano(m1, m2, tolerancia=1000):
    """Compara dos montos con tolerancia absoluta ($1000 COP por defecto)"""
    if m1 == 0 or m2 == 0: return False
    return abs(abs(m1) - abs(m2)) <= tolerancia

def desc_match_keywords(pdf_desc, keywords):
    """Verifica si la descripcion del PDF contiene alguna de las keywords"""
    d = pdf_desc.upper()
    for kw in keywords:
        if kw.upper() in d: return True
    return False

# ============================================================
# 1. CARGAR BD ANTIGUA
# ============================================================
def cargar_old():
    print("Cargando BD antigua...")
    conn = sqlite3.connect(OLD_DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT t.uid, t.type, t.amountInDefaultCurrency, t.date, t.comment,
               COALESCE(c.title, 'Sin categoria') as category_name
        FROM "transaction" t
        LEFT JOIN sync_link sl ON sl.entityUid = t.uid AND sl.entityType='Transaction' AND sl.otherType='Category'
        LEFT JOIN category c ON sl.otherUid = c.uid
        WHERE t.isRemoved=0
        ORDER BY t.date
    """)
    seen_uids = set()
    rows = []
    for r in cur.fetchall():
        if r["uid"] in seen_uids: continue
        seen_uids.add(r["uid"])
        rows.append({
            "uid": r["uid"],
            "type": r["type"],
            "amount": r["amountInDefaultCurrency"] / 100.0,
            "date": normalizar_fecha(r["date"]),
            "comment": r["comment"] or "",
            "category": r["category_name"],
        })
    conn.close()
    incomes = [t for t in rows if t["type"] == "Income"]
    expenses = [t for t in rows if t["type"] == "Expense"]
    total_ing = sum(t["amount"] for t in incomes)
    total_egr = sum(t["amount"] for t in expenses)
    print(f"  {len(rows)} tx ({len(incomes)} ing, {len(expenses)} egr)")
    print(f"  Ingresos: ${total_ing:,.0f} | Egresos: ${total_egr:,.0f}")
    return rows, incomes, expenses

# ============================================================
# 2. CARGAR PDFs CON FECHAS NORMALIZADAS
# ============================================================
def cargar_pdfs():
    print("Cargando PDFs...")
    if not os.path.exists(PDF_DB):
        print("  ERROR: DB no encontrada"); return []
    conn = sqlite3.connect(PDF_DB)
    c = conn.cursor()
    cols = [r[1] for r in c.execute("PRAGMA table_info(transacciones)").fetchall()]
    select = [x for x in ["id","fecha","fecha_date","descripcion","valor","saldo","entidad","cuenta","periodo","categoria"] if x in cols]
    c.execute(f"SELECT {','.join(select)} FROM transacciones")
    pdf_tx = []
    for r in c.fetchall():
        row = dict(zip(select, r))
        # Normalize dates
        raw_fecha = str(row.get("fecha_date") or row.get("fecha") or "")
        fecha_norm = normalizar_fecha(raw_fecha)
        pdf_tx.append({
            "id": row.get("id"),
            "fecha": row.get("fecha"),
            "fecha_date": fecha_norm or row.get("fecha"),
            "fecha_norm": fecha_norm,
            "descripcion": row.get("descripcion"),
            "valor": row.get("valor"),
            "entidad": row.get("entidad"),
        })
    conn.close()
    print(f"  {len(pdf_tx)} tx")
    return pdf_tx

# ============================================================
# 3. MATCHING INTELIGENTE
# ============================================================
def match_description(desc, pdf_txs, old_date, old_amt, dias_max=7, tolerancia=1000):
    """Busca match en PDFs por descripcion + monto + fecha"""
    d = desc.lower()
    matches = []
    for pt in pdf_txs:
        pt_date = pt.get("fecha_norm")
        if not pt_date: continue
        diff = fecha_diff(old_date, pt_date)
        if diff > dias_max: continue
        if not monto_cercano(old_amt, abs(pt["valor"]), tolerancia): continue
        pd = pt["descripcion"].lower()
        # Score: 0-100
        score = 0
        # Amount closeness bonus
        amt_diff = abs(abs(pt["valor"]) - old_amt)
        if amt_diff <= 100: score += 30
        elif amt_diff <= 500: score += 20
        elif amt_diff <= 1000: score += 10
        # Date closeness bonus
        if diff == 0: score += 30
        elif diff <= 2: score += 20
        elif diff <= 5: score += 10
        # Description similarity
        words_d = set(d.split())
        words_pd = set(pd.split())
        common = words_d & words_pd
        if len(common) >= 2: score += len(common) * 10
        # Store name matching
        store_keywords = {
            "amazon": ["amazon", "amzn"],
            "mercadolibre": ["mercadopago", "mercado pago", "mpo"],
            "mercadopago": ["mercadopago", "mpo"],
            "tuboleta": ["tuboleta"],
            "papa johns": ["papa johns", "papa jons"],
            "frisby": ["frisby"],
            "starbucks": ["starbucks"],
            "mcdonald": ["mc donald", "mcdonald"],
            "dunkin": ["dunkin"],
            "buffalo": ["bw buffalo", "buffalo"],
            "cinemark": ["cinemark"],
            "juan valdez": ["juan vldez", "juan valdez"],
            "exito": ["exito"],
            "tiendas ara": ["tiendas ara"],
            "tienda d1": ["tienda d1"],
            "chorilongo": ["chorilongo"],
            "templo disco": ["templo disco"],
            "oxxo": ["oxxo"],
            "burger king": ["burger king"],
            "burger master": ["burger master"],
            "wompi": ["wompi"],
            "tecnipagos": ["tecnipagos"],
            "panaderia": ["panaderia"],
            "secretaria": ["secretaria"],
            "inversiones": ["inversiones"],
            "drogarias": ["drogueria", "drogas"],
        }
        for store, kws in store_keywords.items():
            if store in d and desc_match_keywords(pt["descripcion"], kws):
                score += 40
            elif any(kw in d for kw in kws) and any(kw in pd for kw in kws):
                score += 30
        # Para/De name matching
        if d.startswith("para ") or "pago a " in d or "pago para " in d:
            name_from_desc = d.replace("pago a ", "").replace("pago para ", "").replace("para ", "").strip().split()[0] if d.strip() else ""
            if name_from_desc and len(name_from_desc) >= 3:
                pd_upper = pt["descripcion"].upper()
                if (pd_upper.startswith("PARA ") and name_from_desc.upper() in pd_upper) or \
                   (pd_upper.startswith("DE ") and name_from_desc.upper() in pd_upper):
                    score += 35
        matches.append((pt, diff, score))
    matches.sort(key=lambda x: -x[2])
    return matches

def match_transfer(desc, pdf_txs, old_date, old_amt, dias_max=7, tolerancia=1000):
    """Busca match especifico para transferencias (Para/De [NAME])"""
    d = desc.lower().strip()
    # Extract recipient name from description
    name = ""
    for prefix in ["pago a ", "pago para ", "para "]:
        if d.startswith(prefix):
            name = d[len(prefix):].strip()
            break
    if not name: return []
    
    name_first = name.split()[0] if name.split() else ""
    matches = []
    for pt in pdf_txs:
        pt_date = pt.get("fecha_norm")
        if not pt_date: continue
        diff = fecha_diff(old_date, pt_date)
        if diff > dias_max: continue
        if not monto_cercano(old_amt, abs(pt["valor"]), tolerancia): continue
        pd = pt["descripcion"].upper()
        # Check if PDF has a transaction to/from this person
        name_upper = name.upper()
        name_first_upper = name_first.upper()
        if (pd.startswith("PARA ") or pd.startswith("DE ")):
            pdf_name = pd[4:].strip() if pd.startswith("PARA ") else pd[3:].strip() if pd.startswith("DE ") else ""
            pdf_first = pdf_name.split()[0] if pdf_name.split() else ""
            # Check name match
            if name_first_upper == pdf_first or name_upper in pdf_name or pdf_name in name_upper:
                matches.append((pt, diff, 100 - diff))
    matches.sort(key=lambda x: -x[2])
    return matches

# ============================================================
# 4. CLASIFICACION INTELIGENTE
# ============================================================
def clasificar(comment, category, monto, tipo):
    d = comment.lower().strip()
    
    if not d:
        if tipo == "Income":
            return ("Ingreso/General", "Ingreso")
        return ("Gasto/General", "Efectivo")
    
    # Cash food expenses (small amounts)
    cash_food = ["onces", "papas", "speed", "pito", "gaseosa", "tinto",
                 "choclitos", "almohabana", "perro caliente", "perro y "]
    if any(kw in d for kw in cash_food):
        return ("Efectivo/Comida", "Efectivo")
    
    if tipo == "Income":
        if "quincena" in d or "salario" in d or "nomina" in d:
            return ("Ingreso/Salario", "Ingreso")
        return ("Ingreso/Varios", "Ingreso")
    
    # Expenses by description
    if "spotify" in d: return ("Suscripcion/Spotify", "Tarjeta/Nequi")
    if "netflix" in d: return ("Suscripcion/Netflix", "Tarjeta/Nequi")
    if "google" in d: return ("Suscripcion/Google", "Tarjeta/Nequi")
    if "recarga" in d: return ("Recarga/Telefono", "Tarjeta/Nequi")
    if "gasolina" in d: return ("Transporte/Gasolina", "Tarjeta/Nequi")
    if "préstamo nequi" in d or "prestamo nequi" in d: return ("Prestamo/Nequi", "Tarjeta/Nequi")
    
    if d.startswith("pago a ") or d.startswith("pago para ") or d.startswith("para "):
        return ("Transferencia/Persona", "Nequi")
    
    if "préstamo" in d or "prestamo" in d or "cuota" in d:
        if "nequi" not in d: return ("Prestamo/Personas", "Nequi")
    
    if "internet" in d or "recibo" in d: return ("Servicios/Internet", "Tarjeta/Nequi")
    if d.startswith("pago de "): return ("Servicios/Pago", "Tarjeta/Nequi")
    
    # Map from old category
    cat_map = {
        "Alimentación": ("Efectivo/Comida", "Efectivo"),
        "Alimentacion": ("Efectivo/Comida", "Efectivo"),
        "Moto": ("Transporte/Moto", "Efectivo"),
        "Transporte": ("Transporte/General", "Efectivo"),
        "Servicios digitales": ("Suscripcion/Otros", "Tarjeta/Nequi"),
        "Educación": ("Educacion/General", "Efectivo"),
        "Educacion": ("Educacion/General", "Efectivo"),
        "Salud": ("Salud/General", "Efectivo"),
        "Ropa": ("Ropa/Accesorios", "Efectivo"),
        "Regalos": ("Gastos/Regalos", "Efectivo"),
        "Regalo": ("Gastos/Regalos", "Efectivo"),
        "Otros": ("Gastos/Varios", "Efectivo"),
        "Casa": ("Servicios/Hogar", "Tarjeta/Nequi"),
        "Ahorros": ("Gasto/Ahorros", "Efectivo"),
        "Prestamos que hago": ("Prestamo/Personas", "Nequi"),
        "Prestamos a mi": ("Prestamo/Recibido", "Nequi"),
        "Saldos": ("Gasto/Saldos", "Efectivo"),
        "Mercado": ("Supermercado/General", "Efectivo"),
        "Paseito": ("Viaje/Paseito", "Tarjeta/Nequi"),
        "Salidas": ("Salidas/General", "Tarjeta/Nequi"),
        "Negocio": ("Negocio/Compras", "Tarjeta/Nequi"),
        "Rutina": ("Salud/Rutina", "Tarjeta/Nequi"),
        "Trago": ("Salidas/Trago", "Tarjeta/Nequi"),
        "Estudio": ("Educacion/Estudio", "Tarjeta/Nequi"),
        "Bici": ("Transporte/Bici", "Efectivo"),
    }
    if category in cat_map:
        return cat_map[category]
    
    return ("Gasto/Varios", "Efectivo")

# ============================================================
# 5. REGLAS DE MATCHING CONFIRMADAS
# ============================================================
STORE_RULES = {
    "amazon": {"keywords": ["AMAZON", "AMZN"], "store_type": "ecommerce"},
    "mercadolibre": {"keywords": ["MERCADOPAGO", "MPO", "MERCADO PAGO"], "store_type": "ecommerce"},
    "mercadopago": {"keywords": ["MERCADOPAGO", "MPO"], "store_type": "ecommerce"},
    "tuboleta": {"keywords": ["TUBOLETA"], "store_type": "ecommerce"},
    "papa johns": {"keywords": ["PAPA JOHNS", "PAPA JONS"], "store_type": "restaurant"},
    "frisby": {"keywords": ["FRISBY"], "store_type": "restaurant"},
    "starbucks": {"keywords": ["STARBUCKS"], "store_type": "restaurant"},
    "mcdonald": {"keywords": ["MC DONALD"], "store_type": "restaurant"},
    "dunkin": {"keywords": ["DUNKIN"], "store_type": "restaurant"},
    "buffalo wings": {"keywords": ["BW BUFFALO"], "store_type": "restaurant"},
    "cinemark": {"keywords": ["CINEMARK"], "store_type": "entertainment"},
    "juan valdez": {"keywords": ["JUAN VLDEZ", "JUAN VALDEZ"], "store_type": "restaurant"},
    "exito": {"keywords": ["EXITO"], "store_type": "supermarket"},
    "tiendas ara": {"keywords": ["TIENDAS ARA"], "store_type": "supermarket"},
    "tienda d1": {"keywords": ["TIENDA D1"], "store_type": "supermarket"},
    "chorilongo": {"keywords": ["CHORILONGO"], "store_type": "restaurant"},
    "oxxo": {"keywords": ["OXXO"], "store_type": "store"},
    "burger king": {"keywords": ["BURGUER KING"], "store_type": "restaurant"},
    "wompi": {"keywords": ["WOMPI"], "store_type": "payment"},
    "tecnipagos": {"keywords": ["TECNIPAGOS"], "store_type": "payment"},
    "pse": {"keywords": ["COMPRA PSE"], "store_type": "payment"},
    "templo disco": {"keywords": ["TEMPLO DISCO"], "store_type": "entertainment"},
    "drogueria": {"keywords": ["DROGUERIA", "DROGAS"], "store_type": "pharmacy"},
}

def encontrar_mejor_match(tx, pdf_txs):
    """Encuentra el mejor match en PDFs usando reglas de tiendas + transferencias"""
    d = tx["comment"].lower().strip()
    old_date = tx["date"]
    old_amt = abs(tx["amount"])
    
    # 1. Try store-specific matching first
    for store, rules in STORE_RULES.items():
        if store in d:
            for pt in pdf_txs:
                pt_date = pt.get("fecha_norm")
                if not pt_date: continue
                diff = fecha_diff(old_date, pt_date)
                if diff > 7: continue
                if desc_match_keywords(pt["descripcion"], rules["keywords"]):
                    if monto_cercano(old_amt, abs(pt["valor"]), 1500):
                        return pt, diff, 95
    
    # 2. Try transfer matching (Para/De name)
    for prefix in ["pago a ", "pago para ", "para "]:
        if d.startswith(prefix):
            name = d[len(prefix):].strip().split()[0] if d.strip() else ""
            if name and len(name) >= 3:
                name_u = name.upper()
                for pt in pdf_txs:
                    pt_date = pt.get("fecha_norm")
                    if not pt_date: continue
                    diff = fecha_diff(old_date, pt_date)
                    if diff > 7: continue
                    if not monto_cercano(old_amt, abs(pt["valor"]), 1000): continue
                    pd = pt["descripcion"].upper()
                    if (pd.startswith("PARA ") or pd.startswith("DE ")):
                        pdf_name = pd[4:] if pd.startswith("PARA ") else pd[3:]
                        if name_u in pdf_name or pdf_name.startswith(name_u):
                            return pt, diff, 90
    
    # 3. General description + amount matching
    best = None
    best_score = 0
    for pt in pdf_txs:
        pt_date = pt.get("fecha_norm")
        if not pt_date: continue
        diff = fecha_diff(old_date, pt_date)
        if diff > 7: continue
        if not monto_cercano(old_amt, abs(pt["valor"]), 1500): continue
        
        score = 0
        if diff == 0: score += 30
        elif diff <= 2: score += 20
        elif diff <= 5: score += 10
        
        amt_diff = abs(abs(pt["valor"]) - old_amt)
        if amt_diff <= 100: score += 30
        elif amt_diff <= 500: score += 20
        elif amt_diff <= 1000: score += 10
        
        pd_lower = pt["descripcion"].lower()
        words_d = set(d.split())
        words_pd = set(pd_lower.split())
        common = words_d & words_pd
        score += len(common) * 5
        
        if score > best_score:
            best_score = score
            best = (pt, diff, score)
    
    if best and best_score >= 40:
        return best
    return None

# ============================================================
# 6. CONSTRUIR DB
# ============================================================
def construir_db(all_old, pdf_txs):
    print("\nConstruyendo BD definitiva v2...")
    if os.path.exists(OUT_DB): os.remove(OUT_DB)
    conn = sqlite3.connect(OUT_DB)
    c = conn.cursor()
    
    c.executescript("""
        CREATE TABLE transacciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid TEXT, fuente TEXT DEFAULT 'app_antigua',
            fecha TEXT, fecha_norm TEXT,
            monto REAL, tipo TEXT,
            descripcion TEXT, categoria_old TEXT,
            categoria_final TEXT, metodo_pago TEXT,
            pdf_match_id INTEGER, pdf_match_entidad TEXT,
            pdf_match_desc TEXT, pdf_match_monto REAL,
            pdf_match_fecha TEXT, match_score INTEGER,
            notas TEXT
        );
        CREATE TABLE no_cruzadas (
            uid TEXT PRIMARY KEY,
            fecha TEXT, fecha_norm TEXT,
            monto REAL, tipo TEXT,
            descripcion TEXT, categoria_old TEXT,
            categoria_final TEXT, metodo_pago TEXT,
            notas TEXT
        );
    """)
    
    matched_ids = set()
    cruzadas = 0
    efectivo_count = 0
    
    for tx in all_old:
        cat_final, metodo = clasificar(tx["comment"], tx["category"], tx["amount"], tx["type"])
        d = tx["comment"].lower().strip()
        notas = ""
        
        # Try to match against PDFs (except cash/ingreso)
        match_result = None
        if metodo not in ("Ingreso", "Efectivo") and cat_final not in ("Efectivo/Comida",):
            match_result = encontrar_mejor_match(tx, pdf_txs)
        
        if match_result:
            pt, diff, score = match_result
            monto_norm = normalize_valor(tx.get("amount"), tipo=tx.get("type"))
            pdf_monto_norm = normalize_valor(pt.get("valor"), tipo=pt.get("tipo"))
            c.execute("""
                INSERT INTO transacciones
                (uid, fecha, fecha_norm, monto, tipo, descripcion, categoria_old, categoria_final, metodo_pago,
                 pdf_match_id, pdf_match_entidad, pdf_match_desc, pdf_match_monto, pdf_match_fecha, match_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (tx["uid"], tx["date"], tx["date"], monto_norm, tx["type"],
                  tx["comment"], tx["category"], cat_final, metodo,
                  pt["id"], pt["entidad"], pt["descripcion"][:80], pdf_monto_norm,
                  pt.get("fecha_norm") or pt.get("fecha"), diff))
            matched_ids.add(tx["uid"])
            cruzadas += 1
        else:
            # Mark some as cash
            if metodo == "Efectivo" or cat_final.startswith("Efectivo/"):
                notas = "Pago en efectivo"
                efectivo_count += 1
            elif cat_final == "Gasto/Varios":
                notas = "REVISAR: posible match no encontrado"
            
            monto_norm = normalize_valor(tx.get("amount"), tipo=tx.get("type"))
            c.execute("""
                INSERT INTO no_cruzadas
                (uid, fecha, fecha_norm, monto, tipo, descripcion, categoria_old, categoria_final, metodo_pago, notas)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (tx["uid"], tx["date"], tx["date"], monto_norm, tx["type"],
                  tx["comment"], tx["category"], cat_final, metodo, notas))
    
    conn.commit()
    
    # Stats
    total_tx = c.execute("SELECT COUNT(*) FROM transacciones").fetchone()[0]
    total_nc = c.execute("SELECT COUNT(*) FROM no_cruzadas").fetchone()[0]
    print(f"  Cruzadas: {total_tx}")
    print(f"  No cruzadas: {total_nc}")
    print(f"  De ellas en efectivo: ~{efectivo_count}")
    
    # Export
    exportar_json(conn)
    exportar_csv(conn)
    exportar_txt(conn)
    
    conn.close()
    print(f"  BD: {OUT_DB}")

def exportar_json(conn):
    cur = conn.cursor()
    data = {"transacciones": [], "no_cruzadas": []}
    for table in ["transacciones", "no_cruzadas"]:
        cur.execute(f"SELECT * FROM {table} ORDER BY fecha")
        cols = [d[0] for d in cur.description]
        for row in cur.fetchall():
            d = dict(zip(cols, row))
            for k, v in d.items():
                if isinstance(v, float): d[k] = round(v, 2)
            data[table].append(d)
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)

def exportar_csv(conn):
    cur = conn.cursor()
    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        cur.execute("PRAGMA table_info(transacciones)")
        cols = [r[1] for r in cur.fetchall()]
        w.writerow(cols)
        cur.execute("SELECT * FROM transacciones ORDER BY fecha")
        for row in cur.fetchall():
            w.writerow(row)

def exportar_txt(conn):
    lines = []
    def L(s=""): lines.append(s)
    cur = conn.cursor()
    
    L("=" * 90)
    L("  REPORTE FINANCIERO DEFINITIVO v2")
    L(f"  Fecha: {datetime.now().strftime('%d/%m/%Y')}")
    L("=" * 90)
    
    for tipo_tx, table, label in [("Income", "transacciones", "cruzados"), ("Expense", "transacciones", "cruzados"),
                                    ("Income", "no_cruzadas", "no cruzados"), ("Expense", "no_cruzadas", "no cruzados")]:
        cur.execute(f"SELECT COUNT(*), COALESCE(SUM(monto),0) FROM {table} WHERE tipo='{tipo_tx}'")
        cnt, tot = cur.fetchone()
        if cnt:
            L(f"\n  {label.upper()} ({tipo_tx}): {cnt} tx, ${tot:,.0f}")
    
    L(f"\n{'='*90}")
    L(f"  GASTOS POR CATEGORIA")
    L(f"{'='*90}")
    cur.execute("""
        SELECT categoria_final, metodo_pago, COUNT(*), SUM(monto) FROM (
            SELECT categoria_final, metodo_pago, monto FROM transacciones WHERE tipo='Expense'
            UNION ALL
            SELECT categoria_final, metodo_pago, monto FROM no_cruzadas WHERE tipo='Expense'
        ) GROUP BY categoria_final, metodo_pago ORDER BY SUM(monto) DESC
    """)
    L(f"  {'Categoria':<30s} {'Metodo':<15s} {'Tx':>6s} {'Total':>12s}")
    L(f"  {'-'*30} {'-'*15} {'-'*6} {'-'*12}")
    for r in cur.fetchall():
        L(f"  {r[0]:<30s} {r[1]:<15s} {r[2]:>6d} ${r[3]:>9,.0f}")
    
    L(f"\n{'='*90}")
    L(f"  GASTOS EN EFECTIVO (primeros 30)")
    L(f"{'='*90}")
    cur.execute("""
        SELECT fecha, monto, SUBSTR(descripcion,1,30), categoria_final
        FROM no_cruzadas WHERE metodo_pago='Efectivo' AND tipo='Expense' AND notas LIKE '%efectivo%'
        ORDER BY fecha LIMIT 30
    """)
    for r in cur.fetchall():
        d = r[2] if r[2] else "(sin desc.)"
        L(f"  {r[0]} ${r[1]:>8,.0f} {d:<30s} [{r[3]}]")
    
    # REVISAR
    L(f"\n{'='*90}")
    L(f"  PENDIENTES DE REVISAR")
    L(f"{'='*90}")
    cur.execute("""
        SELECT fecha, monto, descripcion, categoria_final
        FROM no_cruzadas WHERE notas='REVISAR: posible match no encontrado'
        ORDER BY fecha LIMIT 30
    """)
    for r in cur.fetchall():
        L(f"  {r[0]} ${r[1]:>8,.0f} {r[2][:40]:<40s} [{r[3]}]")
    
    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
    with open(OUT_TXT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

# ============================================================
# MAIN
# ============================================================
def main():
    print("=" * 80)
    print("  BD FINANCIERA DEFINITIVA v2")
    print("=" * 80)
    
    all_old, incomes, expenses = cargar_old()
    pdf_txs = cargar_pdfs()
    construir_db(all_old, pdf_txs)
    
    print("\n" + "=" * 80)
    print("  COMPLETADO")
    print("=" * 80)

if __name__ == "__main__":
    main()
