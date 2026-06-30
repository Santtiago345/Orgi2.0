"""
CONSTRUIR BD UNIFICADA DEFINITIVA v3
=====================================
FLUJO:
  1. BASE = TODAS las transacciones de los PDFs (Nequi, Nu, RappiCard)
     - Nequi: movimientos reales de efectivo (base contable)
     - RappiCard/Nu: compras a credito (suplementarias, no se duplican como gasto)
  2. Se deduplican tarjetas de credito (cada compra aparece en multiples extractos)
     - Se identifica: num_cuotas, estado_pago, cuotas_pagadas
  3. Se cruzan las transacciones de MyFinance contra PDFs
     - Match = ya registrado en PDF (no se duplica)
     - No match = efectivo (se agrega a la BD)
  4. Se identifican prestamos Nequi con ID unico
  5. Se genera tabla de cruce con trazabilidad completa

Archivos generados:
  - outputs/db/finanzas_unificada_completa.db
  - outputs/db/finanzas_unificada_completa.json
  - outputs/reports/reporte_financiero_completo.txt
  - outputs/reports/detalle_cruce.csv
"""

import sqlite3, os, re, json, csv
from datetime import datetime, timedelta
from collections import defaultdict

BASE = r"C:\Users\Santt\OneDrive\Documentos\Proyectos\Orgi2.0"
OLD_DB = os.path.join(BASE, "data", "myfinance", "MyFinance.db")
PDF_DB = os.path.join(BASE, "outputs", "db", "finanzas_unificadas.db")
OUT_DB = os.path.join(BASE, "outputs", "db", "finanzas_unificada_completa.db")
OUT_JSON = os.path.join(BASE, "outputs", "db", "finanzas_unificada_completa.json")
OUT_TXT = os.path.join(BASE, "outputs", "reports", "reporte_financiero_completo.txt")
OUT_CSV_CRUCE = os.path.join(BASE, "outputs", "reports", "detalle_cruce.csv")

MESES = {"ENE":1,"FEB":2,"MAR":3,"ABR":4,"MAY":5,"JUN":6,"JUL":7,"AGO":8,"SEP":9,"OCT":10,"NOV":11,"DIC":12}

def normalizar_fecha(s):
    if not s: return None
    s = s.strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s): return s
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", s)
    if m: return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    m = re.match(r"^(\d{2})-(\d{2})-(\d{4})$", s)
    if m: return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    m = re.match(r"^(\d{4})/(\d{2})/(\d{2})$", s)
    if m: return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.match(r"^(\d{1,2})\s+(\w+)\s+(\d{4})$", s)
    if m:
        mon = MESES.get(m.group(2).upper()[:3])
        if mon: return f"{m.group(3)}-{mon:02d}-{int(m.group(1)):02d}"
    return s

def fecha_diff(f1, f2):
    try:
        d1 = datetime.strptime(f1[:10], "%Y-%m-%d")
        d2 = datetime.strptime(f2[:10], "%Y-%m-%d")
        return abs((d1 - d2).days)
    except: return 999

def monto_cercano(m1, m2, tolerancia=1000):
    if m1 == 0 or m2 == 0: return False
    return abs(abs(m1) - abs(m2)) <= tolerancia

def desc_match_keywords(pdf_desc, keywords):
    d = pdf_desc.upper() if pdf_desc else ""
    for kw in keywords:
        if kw.upper() in d: return True
    return False

STORE_RULES = {
    "amazon": {"keywords": ["AMAZON", "AMZN"]},
    "mercadopago": {"keywords": ["MERCADOPAGO", "MPO"]},
    "tuboleta": {"keywords": ["TUBOLETA"]},
    "papa johns": {"keywords": ["PAPA JOHNS", "PAPA JONS"]},
    "frisby": {"keywords": ["FRISBY"]},
    "starbucks": {"keywords": ["STARBUCKS"]},
    "mcdonald": {"keywords": ["MC DONALD"]},
    "dunkin": {"keywords": ["DUNKIN"]},
    "juan valdez": {"keywords": ["JUAN VLDEZ", "JUAN VALDEZ"]},
    "exito": {"keywords": ["EXITO"]},
    "tiendas ara": {"keywords": ["TIENDAS ARA"]},
    "tienda d1": {"keywords": ["TIENDA D1"]},
    "oxxo": {"keywords": ["OXXO"]},
    "burger king": {"keywords": ["BURGUER KING"]},
    "wompi": {"keywords": ["WOMPI"]},
    "templo disco": {"keywords": ["TEMPLO DISCO"]},
    "terpel": {"keywords": ["TERPEL"]},
    "primax": {"keywords": ["PRIMAX", "EDS"]},
    "netflix": {"keywords": ["NETFLIX"]},
    "spotify": {"keywords": ["SPOTIFY"]},
    "google": {"keywords": ["GOOGLE"]},
    "rappipay": {"keywords": ["RAPPIPAY"]},
}

# ============================================================
# 1. CARGAR PDFs CON DEDUP DE TARJETAS
# ============================================================
def cargar_pdfs():
    print("=" * 70)
    print("  PASO 1: Cargando transacciones de PDFs")
    print("=" * 70)
    if not os.path.exists(PDF_DB):
        print("  ERROR: DB no encontrada:", PDF_DB); return []

    conn = sqlite3.connect(PDF_DB)
    c = conn.cursor()
    c.execute("SELECT * FROM transacciones")
    cols = [d[0] for d in c.description]
    
    raw_txs = []
    for r in c.fetchall():
        row = dict(zip(cols, r))
        fecha_norm = normalizar_fecha(str(row.get("fecha_date") or row.get("fecha") or ""))
        fuente = "PDF_Unknown"
        ent = (row.get("entidad") or "").lower()
        if "nequi" in ent: fuente = "Nequi"
        elif "nu" in ent: fuente = "Nu"
        elif "rappi" in ent: fuente = "RappiCard"
        raw_txs.append({
            "pdf_id": row["id"],
            "extracto_id": row.get("extracto_id"),
            "periodo": row.get("periodo", ""),
            "fecha": fecha_norm or row.get("fecha", ""),
            "monto": abs(row["valor"]),
            "monto_raw": row["valor"],
            "descripcion": row.get("descripcion", "").strip(),
            "entidad": row.get("entidad", ""),
            "fuente": fuente,
            "es_ingreso": bool(row.get("es_ingreso", 0)),
            "tipo": "Income" if row.get("es_ingreso") else "Expense",
            "categoria_pdf": row.get("categoria", ""),
        })
    conn.close()
    print(f"  Cargadas {len(raw_txs)} transacciones de PDFs")

    # DEDUP TARJETAS CREDITO: misma compra aparece en N extractos mensuales
    # Identificar grupos de compras unicas por (descripcion, monto)
    grupos_tc = defaultdict(list)
    for t in raw_txs:
        if t["fuente"] in ("RappiCard", "Nu"):
            key = (t["descripcion"].upper(), round(t["monto"], 0))
            grupos_tc[key].append(t)
    
    # Para cada grupo, determinar num_cuotas (cuantos periodos UNICOS aparece)
    compras_dedup = set()
    for key, items in grupos_tc.items():
        periodos_unicos = set()
        for it in items:
            p = it.get("periodo", "")
            if p: periodos_unicos.add(p)
        num_cuotas = len(periodos_unicos)
        
        # Marcar todos los items del grupo (usaremos solo 1 pero marcamos todos)
        for it in items:
            it["num_cuotas"] = num_cuotas
            it["es_tarjeta_credito"] = 1
    
    # Construir lista final: TODOS los Nequi + 1 instancia de cada compra TC
    final = []
    tc_contadas = set()
    for t in raw_txs:
        if t["fuente"] in ("RappiCard", "Nu"):
            key = (t["descripcion"].upper(), round(t["monto"], 0))
            if key in tc_contadas: continue
            tc_contadas.add(key)
            # Keep the FIRST occurrence
        final.append(t)
    
    eliminados = len(raw_txs) - len(final)
    if eliminados > 0:
        print(f"  Deduplicadas tarjetas credito: {eliminados} repetidas eliminadas")
        print(f"    RappiCard: {sum(1 for t in raw_txs if t['fuente']=='RappiCard')} -> {sum(1 for t in final if t['fuente']=='RappiCard')}")
        print(f"    Nu: {sum(1 for t in raw_txs if t['fuente']=='Nu')} -> {sum(1 for t in final if t['fuente']=='Nu')}")
    
    # Determinar ultimo periodo global entre los extractos TC
    all_periodos_tc = set()
    for t in raw_txs:
        if t["fuente"] in ("RappiCard", "Nu") and t.get("periodo"):
            all_periodos_tc.add(t["periodo"])
    ultimo_periodo_tc = max(all_periodos_tc) if all_periodos_tc else ""
    
    # Asignar campos TC a las que quedaron + estado de pago
    for t in final:
        if t["fuente"] in ("RappiCard", "Nu"):
            key = (t["descripcion"].upper(), round(t["monto"], 0))
            gi = grupos_tc.get(key, [])
            if gi:
                num_c = gi[0].get("num_cuotas", 1)
                t["num_cuotas"] = num_c
                t["es_tarjeta_credito"] = 1
                # Determinar ultimo periodo de esta compra
                periodos_compra = set()
                for it in gi:
                    if it.get("periodo"): periodos_compra.add(it["periodo"])
                ultimo_periodo_compra = max(periodos_compra) if periodos_compra else ""
                # Estado: en_curso si aparece en el ultimo periodo global y tiene >1 cuota
                if num_c > 1 and ultimo_periodo_compra == ultimo_periodo_tc:
                    t["estado_pago"] = "en_curso"
                    t["cuotas_pagadas"] = num_c - 1  # falta la ultima cuota
                else:
                    t["estado_pago"] = "pagada"
                    t["cuotas_pagadas"] = num_c
            else:
                t["num_cuotas"] = 1
                t["es_tarjeta_credito"] = 0
                t["estado_pago"] = "pagada"
                t["cuotas_pagadas"] = 1
        else:
            t["num_cuotas"] = 1
            t["es_tarjeta_credito"] = 0
            t["estado_pago"] = "pagada"
            t["cuotas_pagadas"] = 1
    
    ingresos = [t for t in final if t["es_ingreso"]]
    egresos = [t for t in final if not t["es_ingreso"]]
    print(f"  Total: {len(final)} ({len(ingresos)} ing, {len(egresos)} egr)")
    fuentes = defaultdict(int)
    for t in final: fuentes[t["fuente"]] += 1
    for f, c in sorted(fuentes.items()): print(f"    {f}: {c}")
    fechas = [t["fecha"] for t in final if t["fecha"]]
    if fechas: print(f"  Rango: {min(fechas)[:10]} a {max(fechas)[:10]}")
    return final


# ============================================================
# 2. CARGAR MyFinance
# ============================================================
def cargar_myfinance():
    print("\n" + "=" * 70)
    print("  PASO 2: Cargando MyFinance")
    print("=" * 70)
    if not os.path.exists(OLD_DB):
        print("  ERROR: DB no encontrada:", OLD_DB); return []
    conn = sqlite3.connect(OLD_DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT t.uid, t.type, t.amountInDefaultCurrency, t.date, t.comment,
               COALESCE(c.title, 'Sin categoria') as category_name
        FROM "transaction" t
        LEFT JOIN sync_link sl ON sl.entityUid = t.uid AND sl.entityType='Transaction' AND sl.otherType='Category'
        LEFT JOIN category c ON sl.otherUid = c.uid
        WHERE t.isRemoved=0 ORDER BY t.date
    """)
    seen = set()
    rows = []
    for r in cur.fetchall():
        if r["uid"] in seen: continue
        seen.add(r["uid"])
        rows.append({
            "uid": r["uid"], "type": r["type"],
            "amount": r["amountInDefaultCurrency"] / 100.0,
            "date": normalizar_fecha(r["date"]),
            "comment": r["comment"] or "",
            "category": r["category_name"],
        })
    conn.close()
    ing = [t for t in rows if t["type"] == "Income"]
    egr = [t for t in rows if t["type"] == "Expense"]
    print(f"  {len(rows)} tx ({len(ing)} ing, ${sum(t['amount'] for t in ing):,.0f} | {len(egr)} egr, ${sum(t['amount'] for t in egr):,.0f})")
    return rows


# ============================================================
# 3. ANALISIS DE PRESTAMOS NEQUI
# ============================================================
def analizar_prestamos(pdf_txs):
    """Identifica prestamos Nequi y asigna prestamo_id"""
    conn = sqlite3.connect(PDF_DB)
    c = conn.cursor()
    c.execute("SELECT fecha, descripcion, valor, id FROM transacciones WHERE entidad LIKE '%nequi%' AND (descripcion LIKE '%DESEMBOLSO%' OR descripcion LIKE '%PAGO%CREDITO%' OR descripcion LIKE '%PAGO%PRESTAMO%' OR descripcion LIKE '%PAGO TOTAL%' OR descripcion LIKE '%PAGO ADELANTADO%' OR descripcion LIKE '%CUOTA%') ORDER BY fecha")
    loans_raw = c.fetchall()
    conn.close()
    
    # Identificar prestamos: cada DESEMBOLSO es un prestamo nuevo
    prestamo_id_counter = 0
    prestamo_map = {}  # pdf_id -> prestamo_id
    current_prestamo = None
    
    for r in loans_raw:
        fecha, desc, valor, pid = r
        d = (desc or "").upper()
        if "DESEMBOLSO" in d:
            prestamo_id_counter += 1
            pid_str = f"NEQUI_LOAN_{prestamo_id_counter:03d}"
            current_prestamo = pid_str
        if current_prestamo:
            prestamo_map[pid] = current_prestamo
    
    # Apply prestamo_id to pdf_txs
    for t in pdf_txs:
        t["prestamo_id"] = prestamo_map.get(t["pdf_id"])
    
    if prestamo_id_counter > 0:
        print(f"\n  Prestamos Nequi identificados: {prestamo_id_counter}")
        for pid_str in sorted(set(prestamo_map.values())):
            cnt = sum(1 for v in prestamo_map.values() if v == pid_str)
            print(f"    {pid_str}: {cnt} transacciones")
    return prestamo_map


# ============================================================
# 4. MATCHING
# ============================================================
def indexar_por_fecha(pdf_list):
    idx = defaultdict(list)
    for pt in pdf_list:
        f = pt.get("fecha", "")
        if len(f) >= 7: idx[f[:7]].append(pt)
    return idx

def encontrar_match(tx, pdf_list, pdf_idx):
    d = tx["comment"].lower().strip()
    old_date = tx["date"]
    old_amt = abs(tx["amount"])
    tx_tipo = tx["type"]
    if not old_date or not d: return None
    try:
        d0 = datetime.strptime(old_date[:10], "%Y-%m-%d")
        meses = set()
        for delta in range(-7, 8):
            dd = d0 + timedelta(days=delta)
            meses.add(dd.strftime("%Y-%m"))
    except: return None
    
    best = None
    best_score = 0
    cands = []
    for mes in meses: cands.extend(pdf_idx.get(mes, []))
    
    for pt in cands:
        pt_date = pt.get("fecha")
        if not pt_date: continue
        if tx_tipo != pt["tipo"]: continue
        diff = abs((d0 - datetime.strptime(pt_date[:10], "%Y-%m-%d")).days)
        if diff > 7: continue
        if not monto_cercano(old_amt, pt["monto"], 1500): continue
        
        pd = pt["descripcion"].upper() if pt["descripcion"] else ""
        score = 0
        metodo = "monto_fecha"
        if diff == 0: score += 25
        elif diff <= 2: score += 15
        elif diff <= 5: score += 5
        amt_diff = abs(pt["monto"] - old_amt)
        if amt_diff <= 100: score += 25
        elif amt_diff <= 500: score += 15
        elif amt_diff <= 1000: score += 5
        for store, rules in STORE_RULES.items():
            if store in d and desc_match_keywords(pt["descripcion"], rules["keywords"]):
                score += 40; metodo = "tienda"; break
        if tx_tipo == "Income" and any(kw in d for kw in ["quincena","salario","nomina"]):
            if "JUAN MANUEL GARCIA" in pd: score += 45; metodo = "salario"
        for prefix in ["pago a ","pago para ","para "]:
            if d.startswith(prefix):
                name = d[len(prefix):].strip().split()[0] if d.strip() else ""
                if name and len(name) >= 3 and (pd.startswith("PARA ") or pd.startswith("DE ")):
                    pdf_name = pd[4:] if pd.startswith("PARA ") else pd[3:]
                    if name.upper() == pdf_name.split()[0] or name.upper() in pdf_name:
                        score += 40; metodo = "transferencia"
                break
        if any(kw in d for kw in ["prstamo nequi","prestamo nequi","cuota"]):
            if "PAGO" in pd and ("CUOTA" in pd or "CREDITO" in pd or "ADELANTADO" in pd):
                score += 35; metodo = "prestamo_nequi"
        words_d = set(d.split())
        words_pd = set(pd.lower().split())
        score += len(words_d & words_pd) * 2
        if score > best_score: best_score = score; best = (pt["pdf_id"], metodo, score)
    
    if best and best_score >= 30: return best
    return None


# ============================================================
# 5. CLASIFICACION EFECTIVO
# ============================================================
def clasificar_efectivo(comment, category, monto, tipo):
    d = comment.lower().strip()
    if tipo == "Income": return ("Ingreso/Varios", "Efectivo")
    if not d: return ("Gasto/General", "Efectivo")
    cash_food = ["onces","papas","speed","pito","gaseosa","tinto","choclitos","almohabana","perro caliente"]
    if any(kw in d for kw in cash_food): return ("Efectivo/Comida", "Efectivo")
    if "spotify" in d: return ("Suscripcion/Spotify", "Efectivo")
    if "netflix" in d: return ("Suscripcion/Netflix", "Efectivo")
    if "google" in d: return ("Suscripcion/Google", "Efectivo")
    if "recarga" in d: return ("Recarga/Telefono", "Efectivo")
    if "gasolina" in d: return ("Transporte/Gasolina", "Efectivo")
    if "internet" in d or "recibo" in d: return ("Servicios/Internet", "Efectivo")
    if d.startswith("pago a ") or d.startswith("pago para ") or d.startswith("para "):
        return ("Transferencia/Persona", "Efectivo")
    cat_map = {
        "Alimentaci\u00f3n": ("Efectivo/Comida", "Efectivo"),
        "Alimentacion": ("Efectivo/Comida", "Efectivo"),
        "Moto": ("Transporte/Moto", "Efectivo"),
        "Transporte": ("Transporte/General", "Efectivo"),
        "Educaci\u00f3n": ("Educacion/General", "Efectivo"),
        "Educacion": ("Educacion/General", "Efectivo"),
        "Salud": ("Salud/General", "Efectivo"),
        "Ropa": ("Ropa/Accesorios", "Efectivo"),
        "Regalos": ("Gastos/Regalos", "Efectivo"),
        "Regalo": ("Gastos/Regalos", "Efectivo"),
        "Otros": ("Gastos/Varios", "Efectivo"),
        "Casa": ("Servicios/Hogar", "Efectivo"),
        "Ahorros": ("Gasto/Ahorros", "Efectivo"),
        "Prestamos que hago": ("Prestamo/Personas", "Efectivo"),
        "Prestamos a mi": ("Prestamo/Recibido", "Efectivo"),
        "Saldos": ("Gasto/Saldos", "Efectivo"),
        "Mercado": ("Supermercado/General", "Efectivo"),
        "Paseito": ("Viaje/Paseito", "Efectivo"),
        "Salidas": ("Salidas/General", "Efectivo"),
        "Negocio": ("Negocio/Compras", "Efectivo"),
        "Rutina": ("Salud/Rutina", "Efectivo"),
        "Trago": ("Salidas/Trago", "Efectivo"),
        "Estudio": ("Educacion/Estudio", "Efectivo"),
        "Bici": ("Transporte/Bici", "Efectivo"),
        "Servicios digitales": ("Suscripcion/Otros", "Efectivo"),
    }
    if category in cat_map: return cat_map[category]
    return ("Gasto/Varios", "Efectivo")


# ============================================================
# 6. CONSTRUIR BD
# ============================================================
def construir_bd(pdf_txs, app_txs, cruces, prestamo_map):
    print("\n" + "=" * 70)
    print("  PASO 3: Construyendo BD unificada final")
    print("=" * 70)
    
    if os.path.exists(OUT_DB): os.remove(OUT_DB)
    conn = sqlite3.connect(OUT_DB)
    c = conn.cursor()
    
    c.executescript("""
        CREATE TABLE transacciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT, monto REAL, descripcion TEXT,
            tipo TEXT, categoria TEXT, metodo_pago TEXT,
            fuente TEXT,
            pdf_original_id INTEGER, app_uid TEXT, entidad TEXT,
            es_tarjeta_credito INTEGER DEFAULT 0,
            num_cuotas INTEGER DEFAULT 1,
            cuotas_pagadas INTEGER DEFAULT 1,
            estado_pago TEXT DEFAULT 'pagada',
            prestamo_id TEXT,
            notas TEXT
        );
        CREATE TABLE cruce (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            app_uid TEXT, pdf_id INTEGER,
            app_monto REAL, app_desc TEXT,
            pdf_monto REAL, pdf_desc TEXT,
            metodo_matching TEXT, score INTEGER, notas TEXT
        );
    """)
    
    app_by_uid = {tx["uid"]: tx for tx in app_txs}
    pdf_by_id = {pt["pdf_id"]: pt for pt in pdf_txs}
    app_uids_match = set(c[0] for c in cruces)
    
    # PRIMERO: Insertar PDFs con campos TC y prestamo
    for pt in pdf_txs:
        c.execute("""
            INSERT INTO transacciones (fecha, monto, descripcion, tipo, categoria, metodo_pago,
                fuente, pdf_original_id, app_uid, entidad,
                es_tarjeta_credito, num_cuotas, cuotas_pagadas, estado_pago, prestamo_id, notas)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?)
        """, (
            pt["fecha"][:10], pt["monto"], pt["descripcion"][:200],
            pt["tipo"], pt.get("categoria_pdf", ""),
            f"Tarjeta/{pt['fuente']}",
            pt["fuente"], pt["pdf_id"], pt["entidad"],
            pt.get("es_tarjeta_credito", 0), pt.get("num_cuotas", 1),
            pt.get("cuotas_pagadas", 1), pt.get("estado_pago", "pagada"),
            pt.get("prestamo_id"),
            'Compra a credito' if pt.get("es_tarjeta_credito") else 'Transaccion de extracto bancario'
        ))
    
    # SEGUNDO: Agregar efectivo (MyFinance sin match)
    for tx in app_txs:
        if tx["uid"] in app_uids_match: continue
        cat_final, metodo = clasificar_efectivo(tx["comment"], tx["category"], tx["amount"], tx["type"])
        c.execute("""
            INSERT INTO transacciones (fecha, monto, descripcion, tipo, categoria, metodo_pago,
                fuente, pdf_original_id, app_uid, entidad,
                es_tarjeta_credito, num_cuotas, cuotas_pagadas, estado_pago, prestamo_id, notas)
            VALUES (?, ?, ?, ?, ?, ?, 'Efectivo', NULL, ?, NULL,
                0, 1, 1, 'pagada', NULL, 'Pago en efectivo')
        """, (tx["date"][:10], tx["amount"], tx["comment"][:200], tx["type"],
              cat_final, metodo, tx["uid"]))
    
    # TERCERO: Tabla de cruce
    for app_uid, pdf_id, metodo, score in cruces:
        app_tx = app_by_uid.get(app_uid, {})
        pdf_pt = pdf_by_id.get(pdf_id, {})
        c.execute("""INSERT INTO cruce (app_uid, pdf_id, app_monto, app_desc, pdf_monto, pdf_desc, metodo_matching, score, notas)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (app_uid, pdf_id, app_tx.get("amount",0), (app_tx.get("comment","") or "")[:200],
             pdf_pt.get("monto",0), (pdf_pt.get("descripcion","") or "")[:200],
             metodo, score, f"Cruce x {metodo} (score:{score})"))
    
    conn.commit()
    
    # Stats
    total_pdf = c.execute("SELECT COUNT(*) FROM transacciones WHERE fuente != 'Efectivo'").fetchone()[0]
    total_efectivo = c.execute("SELECT COUNT(*) FROM transacciones WHERE fuente = 'Efectivo'").fetchone()[0]
    total_tc = c.execute("SELECT COUNT(*) FROM transacciones WHERE es_tarjeta_credito=1").fetchone()[0]
    total_cruces = c.execute("SELECT COUNT(*) FROM cruce").fetchone()[0]
    total = c.execute("SELECT COUNT(*) FROM transacciones").fetchone()[0]
    total_prestamos = c.execute("SELECT COUNT(DISTINCT prestamo_id) FROM transacciones WHERE prestamo_id IS NOT NULL").fetchone()[0]
    
    print(f"  PDFs: {total_pdf} | Efectivo: {total_efectivo} | TC: {total_tc} | Prestamos: {total_prestamos}")
    print(f"  Cruces: {total_cruces} | TOTAL: {total}")
    
    c.execute("SELECT COUNT(*), COALESCE(SUM(monto),0), tipo FROM transacciones GROUP BY tipo")
    for r in c.fetchall(): print(f"    {r[2]}: {r[0]} tx, ${r[1]:,.0f}")
    
    c.execute("SELECT COUNT(*), COALESCE(SUM(monto),0) FROM transacciones WHERE fuente!='Efectivo' AND tipo='Expense'")
    pdf_exp = c.fetchone()
    c.execute("SELECT COUNT(*), COALESCE(SUM(monto),0) FROM transacciones WHERE fuente!='Efectivo' AND tipo='Income'")
    pdf_inc = c.fetchone()
    c.execute("SELECT COUNT(*), COALESCE(SUM(monto),0) FROM transacciones WHERE fuente='Efectivo' AND tipo='Expense'")
    ef_exp = c.fetchone()
    c.execute("SELECT COUNT(*), COALESCE(SUM(monto),0) FROM transacciones WHERE fuente='Efectivo' AND tipo='Income'")
    ef_inc = c.fetchone()
    balance = (pdf_inc[1] or 0) + (ef_inc[1] or 0) - (pdf_exp[1] or 0) - (ef_exp[1] or 0)
    print(f"\n  BALANCE: ${balance:,.0f}")
    
    return conn


# ============================================================
# EXPORTACIONES
# ============================================================
def exportar_json(conn):
    cur = conn.cursor()
    data = {"transacciones": [], "cruce": []}
    for table in ["transacciones"]:
        cur.execute(f"SELECT * FROM {table} ORDER BY fecha")
        cols = [d[0] for d in cur.description]
        for row in cur.fetchall():
            d = dict(zip(cols, row))
            for k, v in d.items():
                if isinstance(v, float): d[k] = round(v, 2)
            data[table].append(d)
    cur.execute("SELECT * FROM cruce")
    cols2 = [d[0] for d in cur.description]
    for row in cur.fetchall():
        data["cruce"].append(dict(zip(cols2, row)))
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    print(f"  JSON: {OUT_JSON}")

def exportar_csv_cruce(conn):
    cur = conn.cursor()
    os.makedirs(os.path.dirname(OUT_CSV_CRUCE), exist_ok=True)
    with open(OUT_CSV_CRUCE, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        cur.execute("""SELECT c.id, c.app_uid, c.app_monto, c.app_desc, c.pdf_monto, c.pdf_desc, c.metodo_matching, c.score
            FROM cruce c ORDER BY c.id""")
        w.writerow(["id","app_uid","app_monto","app_desc","pdf_monto","pdf_desc","metodo","score"])
        for row in cur.fetchall(): w.writerow(row)
    print(f"  CSV cruce: {OUT_CSV_CRUCE}")

def exportar_txt(conn):
    lines = []
    def L(s=""): lines.append(s)
    cur = conn.cursor()
    L("=" * 90)
    L("  REPORTE FINANCIERO COMPLETO - BD UNIFICADA v3")
    L("  Base: Extractos PDF (Nequi, Nu, RappiCard) + Efectivo (MyFinance)")
    L(f"  Fecha: {datetime.now().strftime('%d/%m/%Y')}")
    L("=" * 90)
    total = cur.execute("SELECT COUNT(*) FROM transacciones").fetchone()[0]
    L(f"\n  TOTAL TRANSACCIONES: {total}")
    
    L(f"\n{'='*90}")
    L(f"  RESUMEN ECONOMICO")
    L(f"{'='*90}")
    cur.execute("SELECT COUNT(*), COALESCE(SUM(monto),0) FROM transacciones WHERE tipo='Income'")
    ci, ti = cur.fetchone()
    cur.execute("SELECT COUNT(*), COALESCE(SUM(monto),0) FROM transacciones WHERE tipo='Expense'")
    ce, te = cur.fetchone()
    L(f"  Ingresos: {ci:>5d} tx  ${ti:>10,.0f}")
    L(f"  Egresos:  {ce:>5d} tx  ${te:>10,.0f}")
    L(f"  Balance:                     ${ti-te:>10,.0f}")
    
    L(f"\n{'='*90}")
    L(f"  POR FUENTE")
    L(f"{'='*90}")
    cur.execute("SELECT fuente, COUNT(*), COALESCE(SUM(monto),0) FROM transacciones GROUP BY fuente ORDER BY SUM(monto) DESC")
    for r in cur.fetchall(): L(f"  {r[0]:<20s} {r[1]:>5d} tx  ${r[2]:>10,.0f}")
    
    L(f"\n{'='*90}")
    L(f"  GASTOS POR CATEGORIA")
    L(f"{'='*90}")
    cur.execute("SELECT categoria, COUNT(*), COALESCE(SUM(monto),0) FROM transacciones WHERE tipo='Expense' GROUP BY categoria ORDER BY SUM(monto) DESC")
    L(f"  {'Categoria':<30s} {'Tx':>5s} {'Total':>12s}")
    L(f"  {'-'*30} {'-'*5} {'-'*12}")
    for r in cur.fetchall(): L(f"  {r[0]:<30s} {r[1]:>5d} ${r[2]:>9,.0f}")
    
    L(f"\n{'='*90}")
    L(f"  TARJETAS CREDITO - COMPRAS A CUOTAS")
    L(f"{'='*90}")
    cur.execute("""SELECT fecha, monto, descripcion, num_cuotas, cuotas_pagadas, estado_pago
        FROM transacciones WHERE es_tarjeta_credito=1 AND num_cuotas > 1
        ORDER BY estado_pago, monto DESC""")
    L(f"  {'Fecha':<12s} {'Monto':>8s} {'Descripcion':<40s} {'Cuotas':>6s} {'Pagadas':>7s} {'Estado':>10s}")
    L(f"  {'-'*12} {'-'*8} {'-'*40} {'-'*6} {'-'*7} {'-'*10}")
    for r in cur.fetchall():
        L(f"  {r[0]:<12s} ${r[1]:>6,.0f} {(r[2] or '-')[:38]:<38s} {r[3]:>4d}/{r[3]:<2d} {r[4]:>5d} {r[5]:>10s}")
    
    L(f"\n{'='*90}")
    L(f"  PRESTAMOS NEQUI")
    L(f"{'='*90}")
    cur.execute("SELECT DISTINCT prestamo_id, COUNT(*), SUM(monto) FROM transacciones WHERE prestamo_id IS NOT NULL GROUP BY prestamo_id")
    for r in cur.fetchall():
        L(f"  {r[0]}: {r[1]} tx, ${r[2]:,.0f}")
    
    L(f"\n{'='*90}")
    L(f"  CRUCES MyFinance vs PDFs ({cur.execute('SELECT COUNT(*) FROM cruce').fetchone()[0]})")
    L(f"{'='*90}")
    cur.execute("SELECT metodo_matching, COUNT(*) FROM cruce GROUP BY metodo_matching ORDER BY COUNT(*) DESC")
    for r in cur.fetchall(): L(f"  {r[0]:<20s} {r[1]:>4d}")
    
    L(f"\n{'='*90}")
    L(f"  TRANSACCIONES EN EFECTIVO (top 20)")
    L(f"{'='*90}")
    cur.execute("""SELECT fecha, monto, descripcion, categoria FROM transacciones
        WHERE fuente='Efectivo' AND tipo='Expense' ORDER BY monto DESC LIMIT 20""")
    for r in cur.fetchall(): L(f"  {r[0]} ${r[1]:>8,.0f} {(r[2] or '-')[:40]} [{r[3]}]")
    
    L(f"\n{'='*90}")
    L(f"  CRUCES (primeros 15)")
    L(f"{'='*90}")
    cur.execute("SELECT metodo_matching, app_monto, app_desc, pdf_desc FROM cruce LIMIT 15")
    for r in cur.fetchall():
        L(f"  [{r[0]:<15s}] app: ${r[1]:>6,.0f} {(r[2] or '-')[:20]} -> PDF: {(r[3] or '-')[:35]}")
    
    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)
    with open(OUT_TXT, "w", encoding="utf-8") as f: f.write("\n".join(lines))
    print(f"  TXT: {OUT_TXT}")


# ============================================================
# MAIN
# ============================================================
def main():
    print("=" * 90)
    print("  BD FINANCIERA UNIFICADA DEFINITIVA v3")
    print("  Base: PDFs (Nequi, Nu, RappiCard) + Efectivo (MyFinance)")
    print("  Creditos: dedup x compra, cuotas, estado pago")
    print("  Prestamos Nequi: ID unico")
    print("=" * 90)
    
    pdf_txs = cargar_pdfs()
    if not pdf_txs: return
    
    # Analisis de prestamos
    print("\n" + "=" * 70)
    print("  ANALISIS DE PRESTAMOS NEQUI")
    print("=" * 70)
    prestamo_map = analizar_prestamos(pdf_txs)
    
    app_txs = cargar_myfinance()
    if not app_txs: return
    
    # Matching
    print("\n" + "=" * 70)
    print("  MATCHING MyFinance vs PDFs")
    print("=" * 70)
    pdf_idx = indexar_por_fecha(pdf_txs)
    cruces = []
    pdf_matchados = set()
    for i, tx in enumerate(app_txs):
        if i > 0 and i % 500 == 0: print(f"  {i}/{len(app_txs)}...")
        r = encontrar_match(tx, pdf_txs, pdf_idx)
        if r:
            pid, met, sc = r
            if pid not in pdf_matchados:
                cruces.append((tx["uid"], pid, met, sc))
                pdf_matchados.add(pid)
    print(f"  Match: {len(cruces)} | Sin match: {len(app_txs)-len(cruces)}")
    
    conn = construir_bd(pdf_txs, app_txs, cruces, prestamo_map)
    exportar_json(conn)
    exportar_csv_cruce(conn)
    exportar_txt(conn)
    conn.close()
    
    print("\n" + "=" * 70)
    print("  COMPLETADO")
    print("=" * 70)
    print(f"  BD: {OUT_DB}")
    print(f"  Reporte: {OUT_TXT}")

if __name__ == "__main__":
    main()
