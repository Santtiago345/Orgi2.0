"""
CONSTRUIR BD DEFINITIVA
=======================
- Carga BD antigua (divide /100)
- Carga PDFs (desde DB existente o re-procesa)
- Cruza cada grupo con reglas especificas
- Genera BD unificada final con todos los datos
"""

import sqlite3, os, re, json, csv
from datetime import datetime, timedelta
from collections import defaultdict
from difflib import SequenceMatcher
from utils.normalize import normalize_valor

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OLD_DB = os.path.join(BASE, "data", "myfinance", "MyFinance.db")
PDF_DB = os.path.join(BASE, "outputs", "db", "finanzas_unificadas.db")
OUT_DB = os.path.join(BASE, "outputs", "db", "finanzas_definitiva.db")
OUT_JSON = os.path.join(BASE, "outputs", "db", "finanzas_definitiva.json")
OUT_CSV = os.path.join(BASE, "outputs", "reports", "finanzas_definitiva.csv")
OUT_TXT = os.path.join(BASE, "outputs", "reports", "reporte_definitivo.txt")

# ============================================================
# HELPERS
# ============================================================
def fecha_a_date(s):
    if not s: return None
    for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"]:
        try: return datetime.strptime(s.strip(), fmt).date()
        except: pass
    return None

def norm(s):
    if not s: return ""
    return re.sub(r'[^a-z0-9 ]', ' ', s.strip().lower())

def first_name(full_name):
    """Extrae el primer nombre de un nombre completo"""
    return full_name.strip().split()[0].upper() if full_name.strip() else ""

def nombres_similares(nombre_bd, nombre_pdf):
    """Verifica si un nombre de BD (posible diminutivo/apodo) corresponde a un nombre PDF"""
    nb = norm(nombre_bd)
    np = norm(nombre_pdf)
    if not nb or not np: return False
    # Direct match
    if nb == np: return True
    # One contains the other
    if nb in np or np in nb: return True
    # First name match (ignoring suffixes like -ito, -ita)
    nb_first = nb.split()[0] if nb.split() else nb
    np_first = np.split()[0] if np.split() else np
    # Handle diminutives: andresito -> andres, juanita -> juan, etc.
    for short, long in [(nb_first, np_first), (np_first, nb_first)]:
        if short in long or long in short: return True
        # Handle -ito/-ita suffix
        if short.endswith("ito") or short.endswith("ita"):
            base = short[:-3] if short.endswith("ito") else short[:-3]
            if base and (base == long or long.startswith(base)): return True
        # Handle -ico/-ica suffix (colombian)
        if short.endswith("ico") or short.endswith("ica"):
            base = short[:-3]
            if base and (base == long or long.startswith(base)): return True
    # Sequence matcher for short names
    if len(nb_first) >= 3 and len(np_first) >= 3:
        if SequenceMatcher(None, nb_first[:6], np_first[:6]).ratio() >= 0.7: return True
    return False

def monto_similar(m1, m2, tolerancia=0.02):
    """Compara dos montos con tolerancia porcentual"""
    if m1 == 0 or m2 == 0: return False
    return abs(m1 - m2) / max(abs(m1), abs(m2)) <= tolerancia

# ============================================================
# 1. CARGAR BD ANTIGUA (valores /100)
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
        if r["uid"] in seen_uids: continue  # deduplicate (sync_link can cause dupes)
        seen_uids.add(r["uid"])
        rows.append({
            "uid": r["uid"],
            "type": r["type"],
            "amount_old_raw": r["amountInDefaultCurrency"],
            "amount": r["amountInDefaultCurrency"] / 100.0,
            "date": r["date"],
            "comment": r["comment"] or "",
            "category": r["category_name"],
            "year": int(r["date"][:4]),
            "month": int(r["date"][5:7]),
        })
    conn.close()
    incomes = [t for t in rows if t["type"] == "Income"]
    expenses = [t for t in rows if t["type"] == "Expense"]
    total_ing = sum(t["amount"] for t in incomes)
    total_egr = sum(t["amount"] for t in expenses)
    print(f"  {len(rows)} transacciones ({len(incomes)} ingresos, {len(expenses)} egresos)")
    print(f"  Ingresos: ${total_ing:,.0f} | Egresos: ${total_egr:,.0f}")
    return rows, incomes, expenses

# ============================================================
# 2. CARGAR DATOS DE PDFs
# ============================================================
def cargar_pdfs():
    print("Cargando datos de PDFs...")
    if not os.path.exists(PDF_DB):
        print("  ERROR: No se encuentra la DB de PDFs")
        return [], []
    conn = sqlite3.connect(PDF_DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    # Check available columns
    cols = [r[1] for r in cur.execute("PRAGMA table_info(transacciones)").fetchall()]
    select_cols = [c for c in ["id", "fecha", "fecha_date", "descripcion", "valor", "saldo",
                                "entidad", "cuenta", "periodo", "categoria",
                                "es_cuota", "total_cuotas", "cuota_actual",
                                "es_prestamo", "tipo_prestamo", "prestamo_id"] if c in cols]
    query = f"SELECT {', '.join(select_cols)} FROM transacciones ORDER BY fecha_date"
    cur.execute(query)
    pdf_tx = []
    for r in cur.fetchall():
        row = dict(zip(select_cols, r))
        pdf_tx.append({
            "id": row.get("id"),
            "fecha": row.get("fecha"),
            "fecha_date": row.get("fecha_date"),
            "descripcion": row.get("descripcion"),
            "valor": row.get("valor"),
            "saldo": row.get("saldo"),
            "entidad": row.get("entidad"),
            "cuenta": row.get("cuenta"),
            "periodo": row.get("periodo"),
            "categoria": row.get("categoria"),
            "es_cuota": row.get("es_cuota", 0),
            "es_prestamo": row.get("es_prestamo", 0),
            "tipo_prestamo": row.get("tipo_prestamo"),
            "prestamo_id": row.get("prestamo_id"),
        })
    conn.close()
    print(f"  {len(pdf_tx)} transacciones de PDFs")
    return pdf_tx

# ============================================================
# 3. CLASIFICAR CADA TRANSACCION DE BD ANTIGUA
# ============================================================
def clasificar_old(tx):
    """Clasifica una transaccion de la BD antigua en una categoria definitiva"""
    d = tx["comment"].lower().strip()
    amt = tx["amount"]
    cat = tx["category"]
    
    # Empty description + empty category → balance/transfer
    if not d:
        if tx["type"] == "Income":
            return "Ingreso/General" if cat == "Sin categoria" else "Ingreso/General"
        else:
            return "Gasto/General" if cat == "Sin categoria" else "Gasto/General"
    
    # Cash expenses (small, recurring)
    cash_keywords = [
        "onces", "papas", "speed", "pito", "gaseosa", "tinto",
        "choclitos", "almohabana", "perro caliente", "perro y ",
    ]
    if any(kw in d for kw in cash_keywords):
        if amt <= 15000:
            return "Efectivo/Comida"
        return "Efectivo/Comida"
    
    # Income - Salary
    if "quincena" in d:
        return "Ingreso/Salario"
    if "prima" in d and cat in ("Salario",):
        return "Ingreso/Prima"
    if "cesantias" in d or "cesantías" in d:
        return "Ingreso/Cesantias"
    if "bonificacion" in d or "bonificación" in d:
        return "Ingreso/Bonificacion"
    if "salario" in d or "nomina" in d or "nómina" in d:
        return "Ingreso/Salario"
    
    # Income - from people
    if tx["type"] == "Income":
        return "Ingreso/Varios"
    
    # Expenses by keyword
    if "spotify" in d:
        return "Suscripcion/Spotify"
    if "netflix" in d:
        return "Suscripcion/Netflix"
    if "google" in d:
        return "Suscripcion/Google"
    if "recarga" in d:
        return "Recarga/Telefono"
    if "préstamo nequi" in d or "prestamo nequi" in d or "cuota préstamo nequi" in d or "cuota prestamo nequi" in d:
        return "Prestamo/Nequi"
    if "gasolina" in d:
        return "Transporte/Gasolina"
    
    # Ara - solo cuando la descripcion es exactamente "ara" o empieza/termina con ara
    if re.match(r'^(ara\b|.*\bara\b)', d) and cat in ("Alimentación", "Alimentacion", "Mercado"):
        return "Supermercado/Ara"
    
    # Prestamos a personas
    if "préstamo" in d or "prestamo" in d or "cuota" in d:
        if "nequi" not in d:
            return "Prestamo/Personas"
    
    # Internet / Recibos
    if "internet" in d or "recibo" in d or "recibo net" in d:
        return "Servicios/Internet"
    
    # Pago de servicios
    if d.startswith("pago de "):
        return "Servicios/Pago"
    
    # Transfers to people (pago a/para [name] or para [name])
    if d.startswith("pago a ") or d.startswith("pago para ") or d.startswith("para "):
        return "Transferencia/Persona"
    
    # By category from old app
    cat_map = {
        "Alimentación": "Efectivo/Comida",
        "Alimentacion": "Efectivo/Comida",
        "Moto": "Transporte/Moto",
        "Transporte": "Transporte/General",
        "Servicios digitales": "Suscripcion/Otros",
        "Educación": "Educacion/General",
        "Educacion": "Educacion/General",
        "Salud": "Salud/General",
        "Ropa": "Ropa/Accesorios",
        "Regalos": "Gastos/Regalos",
        "Regalo": "Gastos/Regalos",
        "Otros": "Gastos/Varios",
        "Casa": "Servicios/Hogar",
        "Ahorros": "Gasto/Ahorros",
        "Prestamos que hago": "Prestamo/Personas",
        "Prestamos a mi": "Prestamo/Recibido",
        "Saldos": "Gasto/Saldos",
        "Mercado": "Supermercado/General",
    }
    if cat in cat_map:
        return cat_map[cat]
    
    return "Gasto/Varios"

# ============================================================
# 4. MATCHING: QUINCENA / SALARIO
# ============================================================
def match_quincena(old_txs, pdf_txs):
    """Cruza quincenas contra 'De JUAN MANUEL GARCIA' en Nequi"""
    matches = []
    no_match = []
    
    # Filtrar PDFs que son ingresos de JUAN MANUEL GARCIA
    pdf_salarios = [p for p in pdf_txs if p["entidad"] == "nequi" and p["valor"] > 0
                    and "JUAN MANUEL GARCIA" in p["descripcion"].upper()]
    
    for tx in old_txs:
        if tx["comment"].lower().startswith("quincena") or tx["comment"].lower().startswith("mitad de quincena") \
           or tx["comment"].lower().startswith("faltante quincena"):
            matched = False
            tx_date = datetime.strptime(tx["date"], "%Y-%m-%d").date()
            for pt in pdf_salarios:
                pt_date = fecha_a_date(str(pt["fecha_date"] or pt["fecha"]))
                if not pt_date: continue
                diff = abs((pt_date - tx_date).days)
                if diff <= 7 and monto_similar(abs(tx["amount"]), abs(pt["valor"]), tolerancia=0.03):
                    matches.append((tx, pt, diff))
                    matched = True
                    break
            if not matched:
                no_match.append(tx)
    return matches, no_match

# ============================================================
# 5. MATCHING: PRESTAMOS NEQUI
# ============================================================
def match_prestamos(old_txs, pdf_txs):
    """Identifica prestamos Nequi: desembolso (income) y pagos (expense)"""
    # Filtrar transacciones de prestamo en BD antigua
    old_loans = [t for t in old_txs if "préstamo nequi" in t["comment"].lower() or "prestamo nequi" in t["comment"].lower()]
    
    # Filtrar PDFs de prestamo
    pdf_loans = [p for p in pdf_txs if p.get("es_prestamo") or 
                 any(kw in p["descripcion"].upper() for kw in ["DESEMBOLSO", "PRESTAMO", "CREDITO", "PAGO TOTAL DEL CREDITO"])]
    
    matches = []
    for tx in old_loans:
        tx_date = datetime.strptime(tx["date"], "%Y-%m-%d").date()
        tx_amt = abs(tx["amount"])
        for pt in pdf_loans:
            pt_date = fecha_a_date(str(pt["fecha_date"] or pt["fecha"]))
            if not pt_date: continue
            diff = abs((pt_date - tx_date).days)
            if diff <= 60 and monto_similar(tx_amt, abs(pt["valor"]), tolerancia=0.05):
                matches.append((tx, pt, diff))
                break
    return matches, [t for t in old_loans if t not in [m[0] for m in matches]]

# ============================================================
# 6. MATCHING: SUSCRIPCIONES (Spotify, Netflix, Google)
# ============================================================
def match_suscripciones(old_txs, pdf_txs):
    """Cruza suscripciones contra PDFs"""
    results = {}
    for servicio in ["spotify", "netflix", "google"]:
        old_subs = [t for t in old_txs if servicio in t["comment"].lower()]
        pdf_subs = [p for p in pdf_txs if servicio in p["descripcion"].lower() and p["valor"] < 0]
        
        matches = []
        no_match = list(old_subs)
        used_pdf = set()
        
        for tx in old_subs:
            tx_date = datetime.strptime(tx["date"], "%Y-%m-%d").date()
            tx_amt = abs(tx["amount"])
            best = None
            best_diff = 999
            for pi, pt in enumerate(pdf_subs):
                if pi in used_pdf: continue
                pt_date = fecha_a_date(str(pt["fecha_date"] or pt["fecha"]))
                if not pt_date: continue
                diff = abs((pt_date - tx_date).days)
                if diff <= 10 and monto_similar(tx_amt, abs(pt["valor"]), tolerancia=0.05):
                    if diff < best_diff:
                        best_diff = diff
                        best = (pt, pi)
            if best:
                matches.append((tx, best[0], best_diff))
                used_pdf.add(best[1])
                no_match = [t for t in no_match if t["uid"] != tx["uid"]]
        
        results[servicio] = {
            "matches": matches,
            "no_match": no_match,
            "total_old": len(old_subs),
            "total_pdf": len(pdf_subs),
        }
    return results

# ============================================================
# 7. MATCHING: TRANSFERENCIAS A PERSONAS
# ============================================================
def match_personas(old_txs, pdf_txs):
    """
    Cruza transferencias de BD antigua contra 'Para [NAME]' / 'De [NAME]' en Nequi.
    Usa similitud de nombres (diminutivos, apodos) + monto exacto + fecha cercana.
    """
    # Identificar posibles transferencias a personas en BD antigua
    old_personas = []
    for t in old_txs:
        d = t["comment"].lower().strip()
        # Buscar patrones de nombre en la descripcion
        nombres_conocidos = [
            "andres", "andresito", "alejo", "mafe", "cristian", "pipe",
            "sebastian", "david", "carlos", "maria", "natalia", "diego",
            "miguel", "angel", "pablo", "camilo", "karen", "laura",
            "daniel", "santiago", "julian", "felipe", "esteban",
            "nicolas", "alejandra", "valentina", "manuel", "mateo",
            "jose", "juan", "juanita", "sara", "carolina", "gina",
            "paula", "jhony", "jhon", "lizeth", "oscar",
        ]
        for nombre in nombres_conocidos:
            if nombre in d:
                old_personas.append((t, nombre))
                break
    
    # Extraer nombres unicos de los PDFs (Para/De)
    pdf_nombres = {}  # first_name -> [(pt, full_name, tipo)]
    for pt in pdf_txs:
        d = pt["descripcion"].upper()
        if pt["entidad"] != "nequi": continue
        if d.startswith("PARA "):
            name = d[5:].strip()
            fn = first_name(name)
            if fn:
                pdf_nombres.setdefault(fn, []).append((pt, name, "Para"))
        elif d.startswith("DE "):
            name = d[3:].strip()
            fn = first_name(name)
            if fn:
                pdf_nombres.setdefault(fn, []).append((pt, name, "De"))
    
    matches = []
    no_match = []
    
    for tx, nombre_bd in old_personas:
        tx_date = datetime.strptime(tx["date"], "%Y-%m-%d").date()
        tx_amt = abs(tx["amount"])
        tx_is_income = tx["type"] == "Income"
        
        best_match = None
        best_diff = 9999
        
        # Buscar en PDFs por nombre similar
        for fn_pdf, candidates in pdf_nombres.items():
            if not nombres_similares(nombre_bd, fn_pdf): continue
            for pt, full_name, tipo in candidates:
                pt_date = fecha_a_date(str(pt["fecha_date"] or pt["fecha"]))
                if not pt_date: continue
                diff = abs((pt_date - tx_date).days)
                if diff > 365: continue  # max 1 year
                
                # Check direction: Income in old DB should match "De [NAME]" in Nequi (they sent to you)
                # Expense in old DB should match "Para [NAME]" in Nequi (you sent to them)
                if tx_is_income and tipo != "De": continue
                if not tx_is_income and tipo != "Para": continue
                
                if monto_similar(tx_amt, abs(pt["valor"]), tolerancia=0.02):
                    if diff < best_diff:
                        best_diff = diff
                        best_match = (pt, full_name, tipo, diff)
        
        if best_match:
            matches.append((tx, best_match[0], best_match[1], best_match[2], best_match[3]))
        else:
            no_match.append((tx, nombre_bd))
    
    return matches, no_match

# ============================================================
# 8. MATCHING: ARA (supermercado)
# ============================================================
def match_ara(old_txs, pdf_txs):
    """Cruza compras en Ara contra 'COMPRA EN TIENDAS ARA' en PDFs.
       Considera que a veces se registraban 2 compras como 1 sola suma."""
    old_ara = [t for t in old_txs if t["comment"].lower().strip() in ("ara",) 
               or t["comment"].lower().startswith("ara ")
               or t["comment"].lower().endswith(" ara")
               or " ara " in t["comment"].lower()
               or t["comment"].lower().strip() == "ara"]
    # Also include transactions with "ara" in category Alimentacion
    old_ara += [t for t in old_txs if t["comment"].lower().strip() == "ara" 
                or t["comment"].lower().startswith("ara ")
                or " ara " in t["comment"].lower()
                or t["comment"].lower().endswith(" ara")]
    # Deduplicate
    seen = set()
    old_ara_uniq = []
    for t in old_ara:
        if t["uid"] not in seen:
            seen.add(t["uid"])
            old_ara_uniq.append(t)
    
    pdf_ara = [p for p in pdf_txs if "TIENDAS ARA" in p["descripcion"].upper() and p["valor"] < 0]
    
    matches = []
    no_match = []
    used_pdf = set()
    
    for tx in old_ara_uniq:
        tx_date = datetime.strptime(tx["date"], "%Y-%m-%d").date()
        tx_amt = abs(tx["amount"])
        best = None
        best_diff = 999
        
        # Try single match
        for pi, pt in enumerate(pdf_ara):
            if pi in used_pdf: continue
            pt_date = fecha_a_date(str(pt["fecha_date"] or pt["fecha"]))
            if not pt_date: continue
            diff = abs((pt_date - tx_date).days)
            if diff <= 7 and monto_similar(tx_amt, abs(pt["valor"]), tolerancia=0.10):
                if diff < best_diff:
                    best_diff = diff
                    best = (pt, pi, None)
        
        # Try sum of 2 purchases on same day
        if not best:
            for pi1, pt1 in enumerate(pdf_ara):
                if pi1 in used_pdf: continue
                pt1_date = fecha_a_date(str(pt1["fecha_date"] or pt1["fecha"]))
                if not pt1_date: continue
                diff1 = abs((pt1_date - tx_date).days)
                if diff1 > 7: continue
                for pi2, pt2 in enumerate(pdf_ara):
                    if pi2 <= pi1 or pi2 in used_pdf: continue
                    pt2_date = fecha_a_date(str(pt2["fecha_date"] or pt2["fecha"]))
                    if not pt2_date: continue
                    diff2 = abs((pt2_date - tx_date).days)
                    if diff2 > 7: continue
                    suma = abs(pt1["valor"]) + abs(pt2["valor"])
                    if monto_similar(tx_amt, suma, tolerancia=0.10):
                        if min(diff1, diff2) < best_diff:
                            best_diff = min(diff1, diff2)
                            best = (pt1, pi1, (pt2, pi2))
                            break
        
        if best:
            pt, pi, extra = best
            matches.append((tx, pt, extra, best_diff))
            used_pdf.add(pi)
            if extra:
                used_pdf.add(extra[1])
        else:
            no_match.append(tx)
    
    return matches, no_match

# ============================================================
# 9. MATCHING: RECARGAS
# ============================================================
def match_recargas(old_txs, pdf_txs):
    """Cruza recargas contra 'COMPRA DE: PAQUETE' en PDFs"""
    old_rec = [t for t in old_txs if "recarga" in t["comment"].lower()]
    pdf_rec = [p for p in pdf_txs if ("PAQUETE" in p["descripcion"].upper() or "RECARGA" in p["descripcion"].upper())
               and p["valor"] < 0]
    
    matches = []
    no_match = []
    used_pdf = set()
    
    for tx in old_rec:
        tx_date = datetime.strptime(tx["date"], "%Y-%m-%d").date()
        tx_amt = abs(tx["amount"])
        best = None
        best_diff = 999
        for pi, pt in enumerate(pdf_rec):
            if pi in used_pdf: continue
            pt_date = fecha_a_date(str(pt["fecha_date"] or pt["fecha"]))
            if not pt_date: continue
            diff = abs((pt_date - tx_date).days)
            if diff <= 7 and monto_similar(tx_amt, abs(pt["valor"]), tolerancia=0.10):
                if diff < best_diff:
                    best_diff = diff
                    best = (pt, pi)
        if best:
            matches.append((tx, best[0], best_diff))
            used_pdf.add(best[1])
        else:
            no_match.append(tx)
    
    return matches, no_match

# ============================================================
# 10. MATCHING: GASOLINA
# ============================================================
def match_gasolina(old_txs, pdf_txs):
    """Cruza gasolina contra 'EDS PRIMAX', 'EDS TERPEL', etc. en PDFs"""
    old_gas = [t for t in old_txs if "gasolina" in t["comment"].lower()]
    pdf_gas = [p for p in pdf_txs if any(kw in p["descripcion"].upper() for kw in ["PRIMAX", "TERPEL", "EDS "])
               and p["valor"] < 0]
    
    matches = []
    no_match = []
    used_pdf = set()
    
    for tx in old_gas:
        tx_date = datetime.strptime(tx["date"], "%Y-%m-%d").date()
        tx_amt = abs(tx["amount"])
        best = None
        best_diff = 999
        for pi, pt in enumerate(pdf_gas):
            if pi in used_pdf: continue
            pt_date = fecha_a_date(str(pt["fecha_date"] or pt["fecha"]))
            if not pt_date: continue
            diff = abs((pt_date - tx_date).days)
            if diff <= 7 and monto_similar(tx_amt, abs(pt["valor"]), tolerancia=0.10):
                if diff < best_diff:
                    best_diff = diff
                    best = (pt, pi)
        if best:
            matches.append((tx, best[0], best_diff))
            used_pdf.add(best[1])
        else:
            no_match.append(tx)
    
    return matches, no_match

# ============================================================
# 11. CONSTRUIR DB DEFINITIVA
# ============================================================
def construir_db(all_old, pdf_txs, resultados):
    """Construye la base de datos SQLite definitiva"""
    print("\nConstruyendo BD definitiva...")
    if os.path.exists(OUT_DB): os.remove(OUT_DB)
    conn = sqlite3.connect(OUT_DB)
    c = conn.cursor()
    
    c.executescript("""
        CREATE TABLE transacciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid TEXT,
            fuente TEXT DEFAULT 'app_antigua',
            fecha TEXT,
            monto REAL,
            tipo TEXT,
            descripcion TEXT,
            categoria_old TEXT,
            categoria_final TEXT,
            metodo_pago TEXT DEFAULT 'Efectivo',
            pdf_match_id INTEGER,
            pdf_match_entidad TEXT,
            pdf_match_desc TEXT,
            pdf_match_monto REAL,
            pdf_match_fecha TEXT,
            pdf_match_score REAL,
            notas TEXT
        );
        CREATE TABLE cruces (
            old_uid TEXT PRIMARY KEY,
            pdf_id INTEGER,
            pdf_entidad TEXT,
            pdf_descripcion TEXT,
            pdf_monto REAL,
            pdf_fecha TEXT,
            match_tipo TEXT,
            match_score REAL,
            diff_dias INTEGER
        );
        CREATE TABLE no_cruzadas (
            uid TEXT PRIMARY KEY,
            fecha TEXT, monto REAL, tipo TEXT,
            descripcion TEXT, categoria_old TEXT,
            categoria_final TEXT, metodo_pago TEXT,
            notas TEXT
        );
    """)
    
    # Index all matched old UIDs
    matched_uids = set()
    
    # Insert matched transactions
    for match_key, data in resultados.items():
        for item in data.get("matches", []):
            if match_key == "quincena":
                tx, pt, diff = item
            elif match_key == "prestamos":
                tx, pt, diff = item
            elif match_key in ("spotify", "netflix", "google"):
                tx, pt, diff = item
            elif match_key == "personas":
                tx, pt, full_name, tipo, diff = item
            elif match_key == "ara":
                tx, pt, extra, diff = item
            elif match_key in ("recargas", "gasolina"):
                tx, pt, diff = item
            else:
                continue
            
            if tx["uid"] in matched_uids: continue  # ya cruzado por otro matcher
            matched_uids.add(tx["uid"])
            cat_final = clasificar_old(tx)
            
            monto_norm = normalize_valor(tx.get("amount"), tipo=tx.get("type"))
            pdf_monto_norm = normalize_valor(pt.get("valor"), tipo=pt.get("tipo"))
            c.execute("""
                INSERT INTO transacciones
                (uid, fuente, fecha, monto, tipo, descripcion, categoria_old, categoria_final, metodo_pago,
                 pdf_match_id, pdf_match_entidad, pdf_match_desc, pdf_match_monto, pdf_match_fecha, pdf_match_score)
                VALUES (?, 'app_antigua', ?, ?, ?, ?, ?, ?, 'Tarjeta/Nequi',
                        ?, ?, ?, ?, ?, ?)
            """, (
                tx["uid"], tx["date"], monto_norm, tx["type"], tx["comment"],
                tx["category"], cat_final,
                pt["id"], pt["entidad"], pt["descripcion"][:80], pdf_monto_norm,
                pt["fecha_date"] or pt["fecha"], diff
            ))
    
    # Process uncategorized old transactions
    for tx in all_old:
        if tx["uid"] in matched_uids: continue
        cat_final = clasificar_old(tx)
        d = tx["comment"].lower().strip()
        
        # Determine payment method
        d_lower = tx["comment"].lower().strip()
        metodo = "Efectivo"
        if cat_final.startswith("Ingreso/"):
            metodo = "Ingreso"
        elif cat_final in ("Suscripcion/Spotify", "Suscripcion/Netflix", "Suscripcion/Google",
                           "Recarga/Telefono", "Prestamo/Nequi",
                           "Suscripcion/Otros"):
            metodo = "Tarjeta/Nequi"
        elif cat_final.startswith("Transferencia/"):
            metodo = "Nequi"
        elif cat_final.startswith("Prestamo/"):
            metodo = "Nequi"
        elif cat_final.startswith("Servicios/"):
            metodo = "Tarjeta/Nequi"
        
        notas = ""
        if cat_final == "Gasto/Varios":
            notas = "REVISAR: clasificar manualmente"
        
        monto_norm = normalize_valor(tx.get("amount"), tipo=tx.get("type"))
        c.execute("""
            INSERT INTO no_cruzadas
            (uid, fecha, monto, tipo, descripcion, categoria_old, categoria_final, metodo_pago, notas)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (tx["uid"], tx["date"], monto_norm, tx["type"], tx["comment"],
              tx["category"], cat_final, metodo, notas))
    
    conn.commit()
    
    # Summary
    total = c.execute("SELECT COUNT(*) FROM transacciones").fetchone()[0]
    total_nc = c.execute("SELECT COUNT(*) FROM no_cruzadas").fetchone()[0]
    print(f"  Cruzadas: {total}")
    print(f"  No cruzadas (con clasificacion): {total_nc}")
    print(f"  Total: {total + total_nc}")
    
    # Export JSON
    exportar_json(conn)
    exportar_csv(conn)
    exportar_txt(conn)
    
    conn.close()
    print(f"  BD: {OUT_DB}")
    print(f"  JSON: {OUT_JSON}")
    print(f"  CSV: {OUT_CSV}")
    print(f"  TXT: {OUT_TXT}")

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
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)

def exportar_csv(conn):
    cur = conn.cursor()
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        # Header
        cur.execute("PRAGMA table_info(transacciones)")
        cols = [r[1] for r in cur.fetchall()]
        w.writerow(cols)
        cur.execute("SELECT * FROM transacciones ORDER BY fecha")
        for row in cur.fetchall():
            w.writerow(row)

def exportar_txt(conn):
    lines = []
    def L(s=""): lines.append(s)
    
    L("=" * 90)
    L("  REPORTE FINANCIERO DEFINITIVO")
    L(f"  Fecha: {datetime.now().strftime('%d/%m/%Y')}")
    L("=" * 90)
    
    cur = conn.cursor()
    
    # Totals
    cur.execute("SELECT COUNT(*), SUM(monto) FROM transacciones WHERE tipo='Income'")
    cnt_ing, tot_ing = cur.fetchone()
    cur.execute("SELECT COUNT(*), SUM(monto) FROM transacciones WHERE tipo='Expense'")
    cnt_egr, tot_egr = cur.fetchone()
    cur.execute("SELECT COUNT(*), SUM(monto) FROM no_cruzadas WHERE tipo='Income'")
    nc_ing_cnt, nc_ing = cur.fetchone()
    cur.execute("SELECT COUNT(*), SUM(monto) FROM no_cruzadas WHERE tipo='Expense'")
    nc_egr_cnt, nc_egr = cur.fetchone()
    
    L(f"\n  CRUZADOS (con match en PDF):")
    L(f"    Ingresos:  {cnt_ing or 0} tx, ${(tot_ing or 0):,.0f}")
    L(f"    Egresos:   {cnt_egr or 0} tx, ${(tot_egr or 0):,.0f}")
    L(f"\n  NO CRUZADOS (clasificados manualmente):")
    L(f"    Ingresos:  {nc_ing_cnt or 0} tx, ${(nc_ing or 0):,.0f}")
    L(f"    Egresos:   {nc_egr_cnt or 0} tx, ${(nc_egr or 0):,.0f}")
    
    total_ing = (tot_ing or 0) + (nc_ing or 0)
    total_egr = (tot_egr or 0) + (nc_egr or 0)
    L(f"\n  TOTAL GENERAL:")
    L(f"    Ingresos:  ${total_ing:,.0f}")
    L(f"    Egresos:   ${total_egr:,.0f}")
    L(f"    Balance:   ${total_ing - total_egr:,.0f}")
    
    # By category (no_cruzadas)
    L(f"\n{'='*90}")
    L(f"  GASTOS POR CATEGORIA (no cruzados)")
    L(f"{'='*90}")
    cur.execute("""
        SELECT categoria_final, metodo_pago, COUNT(*), SUM(monto)
        FROM no_cruzadas WHERE tipo='Expense'
        GROUP BY categoria_final, metodo_pago
        ORDER BY SUM(monto) DESC
    """)
    L(f"  {'Categoria':<35s} {'Metodo':<15s} {'Tx':>6s} {'Total':>12s}")
    L(f"  {'-'*35} {'-'*15} {'-'*6} {'-'*12}")
    for cat, metodo, cnt, total in cur.fetchall():
        L(f"  {cat:<35s} {metodo:<15s} {cnt:>6d} ${total:>9,.0f}")
    
    # Efectivo detail
    L(f"\n{'='*90}")
    L(f"  GASTOS EN EFECTIVO")
    L(f"{'='*90}")
    cur.execute("""
        SELECT SUBSTR(descripcion, 1, 30), monto, fecha
        FROM no_cruzadas WHERE metodo_pago='Efectivo' AND tipo='Expense'
        ORDER BY fecha LIMIT 30
    """)
    L(f"  {'Descripcion':<30s} {'Monto':>10s} {'Fecha':>12s}")
    L(f"  {'-'*30} {'-'*10} {'-'*12}")
    for r in cur.fetchall():
        L(f"  {r[0]:<30s} ${r[1]:>8,.0f} {r[2]:>12s}")
    
    # Transactions still needing review
    L(f"\n{'='*90}")
    L(f"  SIN CLASIFICAR (revisar)")
    L(f"{'='*90}")
    cur.execute("""
        SELECT fecha, monto, descripcion, categoria_old
        FROM no_cruzadas WHERE categoria_final='Sin clasificar'
        ORDER BY fecha LIMIT 20
    """)
    for r in cur.fetchall():
        L(f"  {r[0]} ${r[1]:>8,.0f} {r[2][:40]:<40s} ({r[3]})")
    
    with open(OUT_TXT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

# ============================================================
# MAIN
# ============================================================
def main():
    print("=" * 80)
    print("  CONSTRUCCION DE BD FINANCIERA DEFINITIVA")
    print("=" * 80)
    
    # 1. Load data
    all_old, incomes, expenses = cargar_old()
    pdf_txs = cargar_pdfs()
    
    # 2. Run matching
    print("\n[1] Cruzando Quincenas/Salario...")
    q_matches, q_nomatch = match_quincena(incomes, pdf_txs)
    print(f"    {len(q_matches)} cruzadas, {len(q_nomatch)} sin match")
    
    print("\n[2] Cruzando Prestamos Nequi...")
    p_matches, p_nomatch = match_prestamos(all_old, pdf_txs)
    print(f"    {len(p_matches)} cruzadas, {len(p_nomatch)} sin match")
    
    print("\n[3] Cruzando Suscripciones...")
    sub_results = match_suscripciones(all_old, pdf_txs)
    for servicio, data in sub_results.items():
        print(f"    {servicio}: {len(data['matches'])}/{data['total_old']} cruzadas")
    
    print("\n[4] Cruzando Transferencias a Personas...")
    per_matches, per_nomatch = match_personas(all_old, pdf_txs)
    print(f"    {len(per_matches)} cruzadas, {len(per_nomatch)} sin match")
    
    print("\n[5] Cruzando ARA...")
    ara_matches, ara_nomatch = match_ara(all_old, pdf_txs)
    print(f"    {len(ara_matches)} cruzadas, {len(ara_nomatch)} sin match")
    
    print("\n[6] Cruzando Recargas...")
    rec_matches, rec_nomatch = match_recargas(all_old, pdf_txs)
    print(f"    {len(rec_matches)} cruzadas, {len(rec_nomatch)} sin match")
    
    print("\n[7] Cruzando Gasolina...")
    gas_matches, gas_nomatch = match_gasolina(all_old, pdf_txs)
    print(f"    {len(gas_matches)} cruzadas, {len(gas_nomatch)} sin match")
    
    # 3. Build unified DB
    resultados = {
        "quincena": {"matches": q_matches},
        "prestamos": {"matches": p_matches},
        **sub_results,
        "personas": {"matches": per_matches},
        "ara": {"matches": ara_matches},
        "recargas": {"matches": rec_matches},
        "gasolina": {"matches": gas_matches},
    }
    
    construir_db(all_old, pdf_txs, resultados)
    
    print("\n" + "=" * 80)
    print("  PROCESO COMPLETADO")
    print("=" * 80)

if __name__ == "__main__":
    main()
