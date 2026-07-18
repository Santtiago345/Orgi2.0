"""
Analisis UNIFICADO de finanzas personales
===========================================
Entidades: Nequi, Nu Bank, RappiCard / Davivienda
- Desbloquea todos los PDFs
- Detecta tipo de PDF automaticamente
- Extrae, clasifica y unifica en una sola DB SQLite
"""
import os, re, json, shutil, sqlite3
import pdfplumber
from pypdf import PdfReader, PdfWriter
from datetime import datetime
from collections import defaultdict

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_DIR, "data")
OUTPUT_DIR = os.path.join(PROJECT_DIR, "outputs")
DB_PATH = os.path.join(OUTPUT_DIR, "db", "finanzas_unificadas.db")
JSON_PATH = os.path.join(OUTPUT_DIR, "db", "finanzas_unificadas.json")
REPORT_PATH = os.path.join(OUTPUT_DIR, "reports", "reporte_financiero.txt")
PASSWORD = "REDACTED_PWD"

UNLOCKED_DIR = os.path.join(OUTPUT_DIR, "unlocked")

def parse_colombian_currency(s):
    """Convierte $1.189.843,45 -> 1189843.45"""
    if not s: return None
    s = s.strip().replace("$", "").replace(" ", "")
    if "." in s and "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except:
        return None

FUENTES = {
    "nequi": os.path.join(DATA_DIR, "nequi"),
    "nu": os.path.join(DATA_DIR, "nu"),
    "rappicard": os.path.join(DATA_DIR, "rappicard"),
}

MESES = ["Enero","Febrero","Marzo","Abril","Mayo","Junio",
         "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]


# ============================================================
# DETECCION DE TIPO
# ============================================================
def detectar_tipo(text):
    if "Extracto de dep" in text and ("Nequi" in text or "depósito" in text or "deposito" in text):
        return "nequi"
    if "Nu Financiera" in text or "ayuda@nu.com.co" in text:
        return "nu"
    if "Davivienda" in text or "RappiCard" in text or "rappicard" in text.lower():
        return "rappicard"
    if "CREDIT_CARD_STATEMENT" in text:
        return "rappicard"
    return "desconocido"


# ============================================================
# DESBLOQUEO
# ============================================================
def unlock_all():
    print("Desbloqueando PDFs...")
    if os.path.exists(UNLOCKED_DIR):
        shutil.rmtree(UNLOCKED_DIR)
    os.makedirs(UNLOCKED_DIR)

    pdfs = []
    for nombre, dirpath in FUENTES.items():
        if not os.path.isdir(dirpath):
            print(f"  AVISO: {dirpath} no existe, saltando")
            continue
        for f in os.listdir(dirpath):
            if f.endswith(".pdf") and f != "unlocked":
                pdfs.append((nombre, os.path.join(dirpath, f)))

    total = len(pdfs)
    unlocked = 0
    errors = []
    for i, (fuente, path) in enumerate(pdfs, 1):
        fname = os.path.basename(path)
        try:
            reader = PdfReader(path)
            if reader.is_encrypted:
                reader.decrypt(PASSWORD)
            writer = PdfWriter()
            for page in reader.pages:
                writer.add_page(page)
            out_name = f"{fuente}_{fname}"
            dst = os.path.join(UNLOCKED_DIR, out_name)
            with open(dst, "wb") as fh:
                writer.write(fh)
            unlocked += 1
            print(f"  [{i}/{total}] [{fuente}] {fname}")
        except Exception as e:
            errors.append(fname)
            print(f"  [{i}/{total}] [{fuente}] {fname} -> ERROR: {e}")
    print(f"  Desbloqueados: {unlocked}/{total}")
    if errors:
        print(f"  Errores: {', '.join(errors)}")
    return unlocked


# ============================================================
# PARSERS
# ============================================================
def parse_nequi(filepath):
    result = {"fuente": "nequi", "tipo": "deposito_bajo_monto", "transacciones": [],
              "periodo": None, "anio": None, "mes": None, "titular": None, "cuenta": None,
              "saldo_anterior": None, "total_abonos": None, "total_cargos": None,
              "saldo_actual": None, "intereses": None}

    with pdfplumber.open(filepath) as pdf:
        text = ""
        for p in pdf.pages:
            t = p.extract_text()
            if t: text += t + "\n"

    pm = re.search(r"per[ií]odo\s+de:\s*(\d{4})/(\d{2})", text)
    if pm:
        result["anio"], result["mes"] = int(pm.group(1)), int(pm.group(2))
        result["periodo"] = f"{result['anio']}/{result['mes']:02d}"
    nm = re.search(r"Extracto.*\n\s*(.+?)(?:\n|$)", text)
    if nm: result["titular"] = nm.group(1).strip()
    am = re.search(r"N[uú]mero\s+de\s+dep[óo]sito[^:]*:\s*(\d+)", text)
    if am: result["cuenta"] = am.group(1)
    for key in ["Saldo anterior", "Total abonos", "Total cargos", "Saldo actual", "intereses pagados"]:
        m = re.search(rf"{re.escape(key)}\s*\$?([\d.,]+)", text)
        if m:
            k = key.lower().replace(" ", "_")
            result[k] = m.group(1)

    in_tx = False
    for line in text.split("\n"):
        if "Fecha del movimiento" in line: in_tx = True; continue
        if not in_tx: continue
        if "Los dep" in line or "Puedes consultar" in line: break
        line = line.strip()
        if not line: continue
        txm = re.match(r"(\d{2}/\d{2}/\d{4})\s+(.+?)\s+\$?(-?[\d,]+\.\d{2})\s+\$?(-?[\d,]+\.\d{2})\s*$", line)
        if not txm: continue
        try:
            v = float(txm.group(3).replace(",", ""))
            s = float(txm.group(4).replace(",", ""))
            if abs(v) > 50_000_000 or abs(s) > 50_000_000: continue
            meses_str = f"{result['anio']}/{result['mes']:02d}" if result['anio'] else ""
            result["transacciones"].append({
                "fecha": txm.group(1), "fecha_date": txm.group(1),
                "descripcion": txm.group(2).strip(), "valor": v, "saldo": s,
                "entidad": "nequi", "cuenta": result["cuenta"],
                "periodo": result["periodo"], "meses_str": meses_str,
            })
        except: pass

    return result


def parse_nu(filepath):
    result = {"fuente": "nu", "tipo": "tarjeta_credito", "transacciones": [],
              "periodo": None, "anio": None, "mes": None, "titular": None,
              "total_pagar": None, "pago_minimo": None, "cupo_total": None,
              "cupo_usado": None, "saldo_anterior": None,
              "interes_corriente": None, "tasa_mensual": None, "tasa_anual_ea": None,
              "fecha_corte": None, "fecha_pago": None}

    with pdfplumber.open(filepath) as pdf:
        text = ""
        for p in pdf.pages:
            t = p.extract_text()
            if t: text += t + "\n"

    nm = re.search(r"Joel\s+Santiago\s+Neuta\s+Jaspe", text, re.IGNORECASE)
    if nm: result["titular"] = "JOEL SANTIAGO NEUTA JASPE"

    for key, alias in [("PAGO MÍNIMO", "pago_minimo"),
                       ("Tu cupo definido", "cupo_total")]:
        m = re.search(rf"{re.escape(key)}\s*\$?([\d.,]+)", text)
        if m: result[alias] = m.group(1)
    if result.get("pago_minimo"):
        result["total_pagar"] = result["pago_minimo"]

    im = re.search(r"Intereses.*?\$?\s*([\d.,]+)", text)
    if im: result["interes_corriente"] = im.group(1)

    pm = re.search(r"(\d+[,.]?\d*)%", text)
    if pm: result["tasa_mensual"] = pm.group(1)

    per = re.search(r"(\d{1,2}\s+\w+)\s*[-–—]\s*(\d{1,2}\s+\w+\s+\d{4})\s*$", text, re.MULTILINE)
    if not per:
        lines = text.split("\n")
        for i, line in enumerate(lines):
            if "periodo facturado" in line.lower() and i + 1 < len(lines):
                per = re.search(r"(\d{1,2}\s+\w+)\s*[-–—]\s*(\d{1,2}\s+\w+\s+\d{4})", lines[i+1])
                if per: break
    if per:
        result["periodo"] = f"{per.group(1)} a {per.group(2)}"
        result["anio"] = int(per.group(2).split()[-1])

    fp = re.search(r"Fecha\s*(?:l[íi]mite\s*de\s*)?pago\s+(\d+\s+\w+\s+\d{4})", text)
    if fp: result["fecha_pago"] = fp.group(1)

    fc = re.search(r"Fecha de corte\s+(\d+\s+\w+\s+\d{4})", text)
    if fc: result["fecha_corte"] = fc.group(1)

    year = result.get("anio")
    if not year:
        ym = re.search(r"(\d{4})[/-]", filepath)
        if ym: year = int(ym.group(1))

    meses = {"ENE":1,"FEB":2,"MAR":3,"ABR":4,"MAY":5,"JUN":6,"JUL":7,"AGO":8,"SEP":9,"OCT":10,"NOV":11,"DIC":12,
             "ENERO":1,"FEBRERO":2,"MARZO":3,"ABRIL":4,"MAYO":5,"JUNIO":6,"JULIO":7,"AGOSTO":8,"SEPTIEMBRE":9,"OCTUBRE":10,"NOVIEMBRE":11,"DICIEMBRE":12}

    for line in text.split("\n"):
        line = line.strip()
        txm = re.match(r"(\d{2})\s+(\w+)\s+(.+?)\s+\$?([\d.,]+)\s+\d+\s+de\s+\d+\s+\$?([\d.,]+)", line)
        if txm:
            day = txm.group(1)
            mon_name = txm.group(2).upper()[:3]
            desc = txm.group(3).strip()
            v = parse_colombian_currency(txm.group(4))
            if v is None or v <= 0 or v >= 50_000_000: continue
            mon_num = meses.get(mon_name)
            if mon_num is None: continue
            fy = year if year else 2026
            fd = f"{fy:04d}-{mon_num:02d}-{day}"
            result["transacciones"].append({
                "fecha": f"{day} {txm.group(2).upper()} {fy}",
                "fecha_date": fd,
                "descripcion": desc,
                "valor": -v,
                "saldo": None,
                "entidad": "nu",
                "cuenta": "Nu Bank",
                "periodo": result["periodo"],
            })

    return result


def parse_rappicard(filepath):
    result = {"fuente": "rappicard", "tipo": "tarjeta_credito", "transacciones": [],
              "periodo": None, "anio": None, "mes": None, "titular": None,
              "total_pagar": None, "pago_minimo": None, "cupo_total": None,
              "cupo_usado": None, "saldo_anterior": None,
              "interes_corriente": None, "tasa_mensual": None, "tasa_anual_ea": None,
              "fecha_corte": None, "fecha_pago": None}

    with pdfplumber.open(filepath) as pdf:
        text = ""
        for p in pdf.pages:
            t = p.extract_text()
            if t: text += t + "\n"

    nm = re.search(r"JOEL\s+SANTIAGO\s+NEUTA\s+JASPE", text)
    if nm: result["titular"] = "JOEL SANTIAGO NEUTA JASPE"

    for pattern, alias in [("Pago total", "total_pagar"),
                           ("Cupo total", "cupo_total"),
                           ("Cupo utilizado", "cupo_usado")]:
        m = re.search(rf"{pattern}[:\s]*\$?\s*([\d.,]+)", text)
        if not m:
            m = re.search(rf"{pattern}\s*\n\s*\$?\s*([\d.,]+)", text)
        if m: result[alias] = m.group(1)

    for line in text.split("\n"):
        m = re.search(r"Pago m[ií]nimo\s+\$?\s*([\d.,]+)", line)
        if m:
            result["pago_minimo"] = m.group(1)
            break
    if not result.get("pago_minimo"):
        m = re.search(r"Pago m.nimo\s*\n\s*\$?\s*([\d.,]+)", text)
        if m: result["pago_minimo"] = m.group(1)

    sa = re.search(r"Saldo periodo anterior\s*\$?\s*([\d.,]+)", text)
    if sa: result["saldo_anterior"] = sa.group(1)

    ic = re.search(r"Intereses corrientes?\s*\$?\s*([\d.,]+)", text)
    if ic: result["interes_corriente"] = ic.group(1)

    tms = re.findall(r"(\d+[,.]\d+)%\s+(\d+[,.]\d+)%", text)
    for tm in tms:
        v1 = parse_colombian_currency(tm[0])
        v2 = parse_colombian_currency(tm[1])
        if v1 and v2 and v1 > 0 and v2 > 0:
            result["tasa_mensual"] = tm[0]
            result["tasa_anual_ea"] = tm[1]
            break

    per_start = re.search(r"Desde\s+(\d+\s+\w+\s+\d{4})", text)
    per_end = re.search(r"Hasta\s+(\d+\s+\w+\s+\d{4})", text)
    if per_start and per_end:
        result["periodo"] = f"{per_start.group(1)} a {per_end.group(1)}"
    if per_start:
        result["fecha_corte"] = per_start.group(1)

    fp = re.search(r"Fecha de pago.*?(?:^|\n)\s*(\d+\s+\w+\s+\d{4})", text, re.DOTALL)
    if not fp:
        fp = re.search(r"Fecha de pago\s*\n\s*(\d+\s+\w+\s+\d{4})", text)
    if fp: result["fecha_pago"] = fp.group(1)

    in_tx = False
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        txm = re.match(r"(?:Virtual|Fisica|F[íi]sica|-)\s+(\d{4}-\d{2}-\d{2})\s+(.+?)\s+\$?([\d.,]+)\s+\$?([\d.,]+)\s+(\d+\s+de\s+\d+)", line)
        if txm:
            desc = txm.group(2).strip()
            v = parse_colombian_currency(txm.group(3))
            if v is not None and v > 0 and v < 50_000_000:
                result["transacciones"].append({
                    "fecha": txm.group(1),
                    "fecha_date": txm.group(1),
                    "descripcion": desc,
                    "valor": -v,
                    "saldo": None,
                    "entidad": "rappicard",
                    "cuenta": "RappiCard Davivienda",
                    "periodo": result["periodo"],
                })
        i += 1

    return result


# ============================================================
# CLASIFICACION
# ============================================================
def clasificar(desc, valor):
    d = desc.upper().strip()
    if valor > 0:
        if "DE JUAN MANUEL GARCIA" in d: return "Sueldo"
        if "OTROS BANCOS DE" in d or "TRANSFIYA DE JOEL" in d: return "Sueldo"
        if "PAGO DE INTERESES" in d or "Pago de Intereses" in desc: return "Intereses"
        if "DESEMBOLSO" in d and "PRESTAMO" in d: return "Préstamo recibido"
        if "DE GINA VANESSA" in d or "DE CAROLINA DEL PILAR" in d: return "Ingreso familiar"
        if d.startswith("DE ") or d.startswith("RECIBI POR"): return "Ingreso personas"
        if "RECARGA" in d: return "Recarga Nequi"
        if "TRANSFIYA" in d: return "Transferencia interna"
        if "REEMBOLSO" in d or "REVERSO" in d: return "Reembolso"
        return "Ingreso sin clasificar"

    # Gastos
    if any(k in d for k in ["TIENDAS ARA","SURTITODO","D1","OXXO","EXITO",
                            "CARULLA","JUMBO","MERCADOPAGO","LA SALCHIPAPERIA",
                            "PAPA JOHNS","MC DONALD","MCDONALD","KFC","RAPPI",
                            "DIDI FOOD","HAMBURGUES","COMIDA","ALIMENTO",
                            "PANADERIA","DUNKIN","SANDWICH"]):
        return "Comida"
    if any(k in d for k in ["KOAJ","HYM","ADIDAS","NIKE","ZARA","TRENDY SHOP",
                            "DOLLARCITY"]):
        return "Ropa"
    if any(k in d for k in ["TIGO","UNE TELCO","NETFLIX","SPOTIFY","BOLD",
                            "CLARO","MOVISTAR","CASHBACK"]):
        return "Servicios"
    if any(k in d for k in ["UNAL","UNIVERSIDAD","ICETEX","MATRICULA",
                            "U. NACIONAL"]):
        return "Educacion"
    if any(k in d for k in ["FARMACIA","DROGUERIA","MEDICO","EPS","CLINICA"]):
        return "Salud"
    if any(k in d for k in ["FORTNITE","EPIC","PLAYSTATION","TUBOLETA",
                            "CINE"]):
        return "Entretenimiento"
    if any(k in d for k in ["APPLE","AMZN","AMAZON","MERCADO LIBRE","LINIO",
                            "ALIEXPRESS"]):
        return "Tecnologia"
    if any(k in d for k in ["VIA MOTOS","TALLER DE","GASOLINA","MOTO",
                            "PRIMAX","ESTACION"]):
        return "Transporte"
    if any(k in d for k in ["PAGO CREDITO","PAGO ADELANTADO","PAGO TOTAL",
                            "CUOTA","PRESTAMO"]) and "DESEMBOLSO" not in d:
        return "Pago préstamo"
    if d.startswith("PARA "): return "Transferencia personas"
    if any(k in d for k in ["RETIRO EN","RETIRO EN CAJERO","RETIRO EN PTM",
                            "corresponsal"]):
        return "Retiro efectivo"
    if "PAGO EN QR" in d or "ENVIO CON BRE-B" in d: return "Transferencia interna"
    if "COMPRA PSE" in d: return "Compra PSE"
    if d.startswith("COMPRA EN ") or d.startswith("COMPRA "): return "Compras general"
    if "MINISO" in d or "CASAMILAS" in d or "ESPACIO NATURA" in d: return "Compras general"
    if "LICORES" in d or "ALCOHOL" in d: return "Compras general"
    if "PAGOS POR PSE" in d: return "Pago tarjeta"
    return "Sin clasificar"


# ============================================================
# PROCESAMIENTO
# ============================================================
def procesar_todo():
    # Unlock
    ok = unlock_all()
    if ok == 0:
        print("No se pudo desbloquear ningun PDF. Abortando.")
        return [], []

    # Parse all
    print("\nProcesando PDFs...")
    todos = []
    for fname in sorted(os.listdir(UNLOCKED_DIR)):
        if not fname.endswith(".pdf"): continue
        path = os.path.join(UNLOCKED_DIR, fname)
        try:
            with pdfplumber.open(path) as pdf:
                text = ""
                for p in pdf.pages:
                    t = p.extract_text()
                    if t: text += t + "\n"
            tipo = detectar_tipo(text)
            if tipo == "nequi":
                data = parse_nequi(path)
            elif tipo == "nu":
                data = parse_nu(path)
            elif tipo == "rappicard":
                data = parse_rappicard(path)
            else:
                print(f"  TIPO NO DETECTADO: {fname}")
                continue
            data["archivo"] = fname
            data["tipo_detectado"] = tipo
            for tx in data["transacciones"]:
                tx["categoria"] = clasificar(tx["descripcion"], tx["valor"])
            todos.append(data)
            tx_count = len(data["transacciones"])
            per = data.get("periodo", "?") or "?"
            print(f"  {fname:50s} -> [{tipo:>10s}] {per:15s}  ({tx_count:3d} tx)")
        except Exception as e:
            print(f"  {fname:50s} -> ERROR: {e}")

    print(f"\nTotal procesados: {len(todos)} archivos")
    total_tx = sum(len(d["transacciones"]) for d in todos)
    print(f"Total transacciones: {total_tx}")
    return todos, total_tx


# ============================================================
# SQLite
# ============================================================
def crear_db(conn):
    conn.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS extractos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            archivo TEXT, fuente TEXT, tipo TEXT,
            periodo TEXT, anio INTEGER, mes INTEGER,
            titular TEXT, cuenta TEXT,
            total_pagar REAL, pago_minimo REAL, cupo_total REAL,
            cupo_usado REAL, saldo_anterior REAL, total_abonos REAL, total_cargos REAL, saldo_actual REAL,
            interes_corriente REAL, tasa_mensual REAL, tasa_anual_ea REAL,
            fecha_corte TEXT, fecha_pago TEXT,
            num_transacciones INTEGER
        );
        CREATE TABLE IF NOT EXISTS transacciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            extracto_id INTEGER REFERENCES extractos(id),
            fecha TEXT, fecha_date TEXT,
            descripcion TEXT, valor REAL, saldo REAL,
            entidad TEXT, cuenta TEXT, periodo TEXT,
            categoria TEXT, es_ingreso INTEGER,
            es_recurrente INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS categorias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE, tipo TEXT
        );
        CREATE TABLE IF NOT EXISTS patrones_recurrentes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT, descripcion TEXT, monto REAL,
            num_ocurrencias INTEGER, entidad TEXT,
            primer_ocurrencia TEXT, ultima_ocurrencia TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_tx_fecha ON transacciones(fecha_date);
        CREATE INDEX IF NOT EXISTS idx_tx_categoria ON transacciones(categoria);
        CREATE INDEX IF NOT EXISTS idx_tx_entidad ON transacciones(entidad);
    """)


def insertar_datos(conn, todos):
    cur = conn.cursor()
    for d in todos:
        cu = d.get("cuenta")
        cur.execute("""
            INSERT INTO extractos
            (archivo, fuente, tipo, periodo, anio, mes, titular, cuenta,
             total_pagar, pago_minimo, cupo_total, cupo_usado,
             saldo_anterior, total_abonos, total_cargos, saldo_actual,
             interes_corriente, tasa_mensual, tasa_anual_ea,
             fecha_corte, fecha_pago, num_transacciones)
            VALUES (?,?,?,?,?,?,?,?,
                    ?,?,?,?,
                    ?,?,?,?,
                    ?,?,?,
                    ?,?,?)
        """, (
            d["archivo"], d["fuente"], d["tipo"],
            d.get("periodo"), d.get("anio"), d.get("mes"), d.get("titular"), cu,
            parse_colombian_currency(d.get("total_pagar")),
            parse_colombian_currency(d.get("pago_minimo")),
            parse_colombian_currency(d.get("cupo_total")),
            parse_colombian_currency(d.get("cupo_usado")),
            parse_colombian_currency(d.get("saldo_anterior")),
            parse_colombian_currency(d.get("total_abonos")),
            parse_colombian_currency(d.get("total_cargos")),
            parse_colombian_currency(d.get("saldo_actual")),
            parse_colombian_currency(d.get("interes_corriente")),
            parse_colombian_currency(d.get("tasa_mensual")),
            parse_colombian_currency(d.get("tasa_anual_ea")),
            d.get("fecha_corte"), d.get("fecha_pago"),
            len(d["transacciones"]),
        ))
        eid = cur.lastrowid
        for tx in d["transacciones"]:
            es_ing = 1 if tx["valor"] > 0 else 0
            cur.execute("""
                INSERT INTO transacciones
                (extracto_id, fecha, fecha_date, descripcion, valor, saldo,
                 entidad, cuenta, periodo, categoria, es_ingreso)
                VALUES (?,?,?,?,?,?, ?,?,?,?, ?)
            """, (eid, tx["fecha"], tx["fecha_date"], tx["descripcion"],
                  tx["valor"], tx.get("saldo"),
                  tx["entidad"], tx.get("cuenta"), tx.get("periodo"),
                  tx["categoria"], es_ing))
    conn.commit()


# ============================================================
# REPORTES
# ============================================================
def generar_reportes(conn, todos):
    cur = conn.cursor()
    lines = []
    def L(s=""): lines.append(s)

    L("=" * 80)
    L("  REPORTE UNIFICADO DE FINANZAS")
    L("  Titular: JOEL SANTIAGO NEUTA JASPE")
    L(f"  Fecha: {datetime.now().strftime('%d/%m/%Y')}")
    L("=" * 80)

    cur.execute("""
        SELECT COUNT(*), SUM(CASE WHEN es_ingreso=1 THEN valor ELSE 0 END),
               SUM(CASE WHEN es_ingreso=0 THEN ABS(valor) ELSE 0 END)
        FROM transacciones
    """)
    total_tx, total_ing, total_egr = cur.fetchone()
    L(f"\n  Total transacciones: {int(total_tx):,}")
    L(f"  Total ingresos:      ${total_ing:>12,.2f}" if total_ing else "  Total ingresos:       $0.00")
    L(f"  Total egresos:       ${total_egr:>12,.2f}" if total_egr else "  Total egresos:        $0.00")
    L(f"  Balance:             ${(total_ing or 0) - (total_egr or 0):>12,.2f}")

    # Por entidad
    L(f"\n{'='*80}")
    L("  POR ENTIDAD")
    L(f"{'='*80}")
    L(f"  {'Entidad':<20s} {'Extractos':>10s} {'Transacciones':>14s} {'Ingresos':>15s} {'Egresos':>15s}")
    L(f"  {'-'*20} {'-'*10} {'-'*14} {'-'*15} {'-'*15}")
    for ent in ["nequi", "nu", "rappicard"]:
        cur.execute("""
            SELECT COUNT(DISTINCT e.id), COUNT(t.id),
                   COALESCE(SUM(CASE WHEN t.es_ingreso=1 THEN t.valor ELSE 0 END), 0),
                   COALESCE(SUM(CASE WHEN t.es_ingreso=0 THEN ABS(t.valor) ELSE 0 END), 0)
            FROM extractos e JOIN transacciones t ON t.extracto_id = e.id
            WHERE e.fuente = ?
        """, (ent,))
        r = cur.fetchone()
        L(f"  {ent:<20s} {r[0]:>10d} {r[1]:>14,d} ${r[2]:>12,.2f} ${r[3]:>12,.2f}")

    # Categorias
    L(f"\n{'='*80}")
    L("  GASTOS POR CATEGORIA")
    L(f"{'='*80}")
    L(f"  {'Categoria':<30s} {'Total':>15s} {'Tx':>8s}")
    L(f"  {'-'*30} {'-'*15} {'-'*8}")
    cur.execute("""
        SELECT categoria, COUNT(*), SUM(ABS(valor))
        FROM transacciones WHERE es_ingreso=0
        GROUP BY categoria ORDER BY SUM(ABS(valor)) DESC
    """)
    for cat, cnt, total in cur.fetchall():
        L(f"  {cat:<30s} ${total:>12,.2f} {cnt:>8d}")

    L(f"\n{'='*80}")
    L("  INGRESOS POR CATEGORIA")
    L(f"{'='*80}")
    L(f"  {'Categoria':<30s} {'Total':>15s} {'Tx':>8s}")
    L(f"  {'-'*30} {'-'*15} {'-'*8}")
    cur.execute("""
        SELECT categoria, COUNT(*), SUM(valor)
        FROM transacciones WHERE es_ingreso=1
        GROUP BY categoria ORDER BY SUM(valor) DESC
    """)
    for cat, cnt, total in cur.fetchall():
        L(f"  {cat:<30s} ${total:>12,.2f} {cnt:>8d}")

    # Patrones recurrentes
    L(f"\n{'='*80}")
    L("  PATRONES DE INGRESO PERIODICO (>=3 ocurrencias)")
    L(f"{'='*80}")
    cur.execute("""
        SELECT descripcion, ROUND(valor, 0), COUNT(*), entidad, MIN(fecha), MAX(fecha)
        FROM transacciones WHERE es_ingreso=1 AND valor > 0
        GROUP BY descripcion, ROUND(valor, 0)
        HAVING COUNT(*) >= 3
        ORDER BY COUNT(*) DESC LIMIT 25
    """)
    L(f"  {'Descripcion':<45s} {'Monto':>10s} {'Veces':>6s}")
    L(f"  {'-'*45} {'-'*10} {'-'*6}")
    for r in cur.fetchall():
        L(f"  {r[0][:44]:<45s} ${r[1]:>8,.0f} {r[2]:>6d}")

    L(f"\n{'='*80}")
    L("  PAGOS RECURRENTES (>=3 ocurrencias)")
    L(f"{'='*80}")
    cur.execute("""
        SELECT descripcion, ROUND(ABS(valor), 0), COUNT(*), entidad, MIN(fecha), MAX(fecha)
        FROM transacciones WHERE es_ingreso=0 AND ABS(valor) > 0
        GROUP BY descripcion, ROUND(ABS(valor), 0)
        HAVING COUNT(*) >= 3
        ORDER BY COUNT(*) DESC LIMIT 30
    """)
    L(f"  {'Descripcion':<45s} {'Monto':>10s} {'Veces':>6s} {'Periodo':>22s}")
    L(f"  {'-'*45} {'-'*10} {'-'*6} {'-'*22}")
    for r in cur.fetchall():
        per = f"{r[4][:10] if r[4] else '?'} -> {r[5][:10] if r[5] else '?'}"
        L(f"  {r[0][:44]:<45s} ${r[1]:>8,.0f} {r[2]:>6d} {per:>22s}")

    # Evolucion mensual
    L(f"\n{'='*80}")
    L("  EVOLUCION MENSUAL - NEQUI")
    L(f"{'='*80}")
    L(f"  {'Periodo':<10s} {'Ingresos':>14s} {'Gastos':>14s} {'Balance':>14s} {'Tx':>6s}")
    L(f"  {'-'*10} {'-'*14} {'-'*14} {'-'*14} {'-'*6}")
    cur.execute("""
        SELECT e.periodo,
               COALESCE(SUM(CASE WHEN t.es_ingreso=1 THEN t.valor ELSE 0 END), 0),
               COALESCE(SUM(CASE WHEN t.es_ingreso=0 THEN ABS(t.valor) ELSE 0 END), 0),
               COUNT(*)
        FROM extractos e JOIN transacciones t ON t.extracto_id = e.id
        WHERE e.fuente = 'nequi'
        GROUP BY e.id ORDER BY e.anio, e.mes
    """)
    for r in cur.fetchall():
        bal = r[1] - r[2]
        L(f"  {str(r[0] or '?'):<10s} ${r[1]:>11,.2f} ${r[2]:>11,.2f} ${bal:>11,.2f} {r[3]:>6d}")

    # Tarjetas de credito
    L(f"\n{'='*80}")
    L("  TARJETAS DE CREDITO - RESUMEN")
    L(f"{'='*80}")
    L(f"  {'Entidad':<15s} {'Periodo':>20s} {'Total pagar':>15s} {'Pago minimo':>15s}")
    L(f"  {'-'*15} {'-'*20} {'-'*15} {'-'*15}")
    cur.execute("""
        SELECT fuente, periodo, total_pagar, pago_minimo
        FROM extractos WHERE fuente IN ('nu','rappicard')
        ORDER BY fuente, anio DESC, mes DESC
    """)
    for r in cur.fetchall():
        tp = f"${r[2]:>10,.2f}" if r[2] else "?"
        pm = f"${r[3]:>10,.2f}" if r[3] else "?"
        L(f"  {str(r[0]):<15s} {str(r[1] or ''):>20s} {tp:>15s} {pm:>15s}")

    report = "\n".join(lines)
    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(report)
    return report


def exportar_json(conn):
    cur = conn.cursor()
    data = {"extractos": [], "transacciones": [], "patrones": []}
    for table in ["extractos", "transacciones"]:
        cur.execute(f"SELECT * FROM {table}")
        cols = [d[0] for d in cur.description]
        for row in cur.fetchall():
            d = dict(zip(cols, row))
            for k, v in d.items():
                if isinstance(v, float):
                    d[k] = round(v, 2)
            data[table].append(d)
    os.makedirs(os.path.dirname(JSON_PATH), exist_ok=True)
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nJSON exportado a: {JSON_PATH}")


# ============================================================
# MAIN
# ============================================================
def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    todos, total_tx = procesar_todo()

    if os.path.exists(DB_PATH):
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.executescript("""
                DROP TABLE IF EXISTS transacciones;
                DROP TABLE IF EXISTS extractos;
                DROP TABLE IF EXISTS categorias;
                DROP TABLE IF EXISTS patrones_recurrentes;
            """)
            conn.commit()
            conn.close()
        except Exception:
            # Si no es posible eliminar el archivo, usamos la ruta existente y regeneramos las tablas.
            pass
    conn = sqlite3.connect(DB_PATH)
    crear_db(conn)
    insertar_datos(conn, todos)

    print(f"\nTransacciones en DB: {conn.execute('SELECT COUNT(*) FROM transacciones').fetchone()[0]}")

    report = generar_reportes(conn, todos)
    exportar_json(conn)

    conn.close()

    print(f"\n{'='*80}")
    print(f"  DB:  {DB_PATH}")
    print(f"  JSON: {JSON_PATH}")
    print(f"  TXT: {REPORT_PATH}")
    print(f"{'='*80}")
    print(report)


if __name__ == "__main__":
    main()
