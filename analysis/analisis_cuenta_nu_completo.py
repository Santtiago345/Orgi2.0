"""
Analisis COMPLETO de extractos Cuenta de Ahorros Nu
"""
import os, re, sqlite3, hashlib
import pdfplumber

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF_DIR = os.path.join(BASE, "data", "cuenta_nu")
DB_PATH = os.path.join(PDF_DIR, "cuenta_nu_finanzas.db")

MESES = {"ENE":1,"FEB":2,"MAR":3,"ABR":4,"MAY":5,"JUN":6,"JUL":7,"AGO":8,"SEP":9,"OCT":10,"NOV":11,"DIC":12,
         "ENERO":1,"FEBRERO":2,"MARZO":3,"ABRIL":4,"MAYO":5,"JUNIO":6,"JULIO":7,"AGOSTO":8,"SEPTIEMBRE":9,"OCTUBRE":10,"NOVIEMBRE":11,"DICIEMBRE":12}

def parse_valor(s):
    if not s: return None
    s = s.strip().replace("$", "").replace("+", "").replace(" ", "")
    if s.endswith("-"): s = "-" + s[:-1]
    if "." in s and "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try: return float(s)
    except: return None

def clasificar_cuenta_nu(desc):
    d = desc.upper().strip()
    if "DEPOSITASTE" in d or "PSE" in d or "RENDIMIENTO" in d:
        return "Ingreso recurrente"
    if "COMPRA EN" in d or "COMPRA" in d:
        return "Compras general"
    if "IMPUESTO" in d or "4X1000" in d:
        return "Cargos financieros"
    if "RETIRO" in d:
        return "Retiro efectivo"
    return "Sin clasificar"

def parse_cuenta_nu_pdf(filepath):
    with pdfplumber.open(filepath) as pdf:
        text = ""
        for p in pdf.pages:
            t = p.extract_text()
            if t: text += t + "\n"

    result = {
        "fuente": "cuenta_nu", "tipo": "cuenta",
        "titular": None, "cuenta": None, "placa": None,
        "periodo": None, "anio": None, "mes": None,
        "saldo_inicial": None, "saldo_final": None,
        "transacciones": [],
    }

    tm = re.search(r"Joel\s+Santiago\s+Neuta\s+Jaspe", text, re.IGNORECASE)
    if tm: result["titular"] = "JOEL SANTIAGO NEUTA JASPE"

    cm = re.search(r"N[uú]mero\s+de\s+Cuenta\s+(\d+)", text, re.IGNORECASE)
    if cm: result["cuenta"] = cm.group(1)

    pm = re.search(r"Nu\s+Placa\s+(\w+)", text, re.IGNORECASE)
    if pm: result["placa"] = pm.group(1)

    pm2 = re.search(r"Per[ií]odo\s+.*?([A-Za-z]+)\s+(\d{4})", text, re.IGNORECASE)
    if pm2:
        mes = MESES.get(pm2.group(1).upper()[:3])
        if mes:
            result["anio"] = int(pm2.group(2))
            result["mes"] = mes
            result["periodo"] = f"{result['anio']}/{mes:02d}"
    if not result.get("periodo"):
        pm2 = re.search(r"Lleg[oó] tu extracto de\s+([A-Za-z]+)", text, re.IGNORECASE)
        if pm2:
            mes = MESES.get(pm2.group(1).upper()[:3])
            if mes:
                ym = re.search(r"(\d{4})", text)
                anio = int(ym.group(1)) if ym else 2024
                result["anio"] = anio
                result["mes"] = mes
                result["periodo"] = f"{anio}/{mes:02d}"
    if not result.get("periodo"):
        m = re.search(r"(\d{4})[_-](\d{2})", filepath)
        if m:
            result["anio"] = int(m.group(1))
            result["mes"] = int(m.group(2))
            result["periodo"] = f"{result['anio']}/{result['mes']:02d}"

    sm = re.search(r"Tu dinero al inicio del mes\s*\$?([\d.,]+)", text)
    if sm: result["saldo_inicial"] = parse_valor(sm.group(1))
    sf = re.search(r"Tu dinero a final del mes\s*\$?([\d.,]+)", text)
    if sf: result["saldo_final"] = parse_valor(sf.group(1))

    for line in text.split("\n"):
        line = line.strip()
        m = re.match(r"(\d{2})\s+(\w{3})\s+(.+?)\s+([+-]\$?[\d.,]+)", line)
        if not m:
            continue
        day = m.group(1)
        mon_name = m.group(2).upper()[:3]
        desc = m.group(3).strip()
        valor_str = m.group(4).strip()

        mon_num = MESES.get(mon_name)
        if mon_num is None:
            continue

        valor = parse_valor(valor_str)
        if valor is None:
            continue

        anio = result["anio"] or 2024
        fecha = f"{anio:04d}-{mon_num:02d}-{day}"

        result["transacciones"].append({
            "fecha": fecha,
            "fecha_date": fecha,
            "descripcion": desc[:100],
            "descripcion_normalizada": re.sub(r'[^A-Z0-9\s]', '', desc.upper()).strip(),
            "valor": valor,
            "categoria": clasificar_cuenta_nu(desc),
            "cuota_actual": 1,
            "total_cuotas": 1,
        })

    return result

def main():
    print("=" * 60)
    print("ANALISIS DE EXTRACTOS CUENTA NU")
    print("=" * 60)

    if not os.path.exists(PDF_DIR):
        os.makedirs(PDF_DIR, exist_ok=True)

    pdfs = [f for f in os.listdir(PDF_DIR) if f.lower().endswith(".pdf")]
    if not pdfs:
        print(f"No hay PDFs en {PDF_DIR}")
        return

    print(f"Encontrados {len(pdfs)} PDF(s)")

    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS extractos (
            id INTEGER PRIMARY KEY,
            archivo TEXT, hash TEXT,
            fuente TEXT, tipo TEXT,
            periodo TEXT, anio INTEGER, mes INTEGER,
            titular TEXT, cuenta TEXT, placa TEXT,
            saldo_inicial REAL, saldo_final REAL,
            num_transacciones INTEGER
        );
        CREATE TABLE IF NOT EXISTS transacciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            extracto_id INTEGER,
            fecha TEXT, fecha_date TEXT,
            descripcion TEXT, descripcion_normalizada TEXT,
            valor REAL, categoria TEXT,
            cuota_actual INTEGER DEFAULT 1,
            total_cuotas INTEGER DEFAULT 1,
            FOREIGN KEY (extracto_id) REFERENCES extractos(id)
        );
    """)
    conn.commit()

    extracto_id = 0
    for fname in sorted(pdfs):
        path = os.path.join(PDF_DIR, fname)
        try:
            file_hash = hashlib.md5(open(path, "rb").read()).hexdigest()
        except:
            file_hash = ""
        data = parse_cuenta_nu_pdf(path)
        if len(data["transacciones"]) == 0:
            print(f"  [SKIP] {fname}: sin transacciones")
            continue
        extracto_id += 1

        c.execute("""INSERT INTO extractos (id, archivo, hash, fuente, tipo, periodo, anio, mes, titular, cuenta, placa, saldo_inicial, saldo_final, num_transacciones)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (extracto_id, fname, file_hash, "cuenta_nu", "cuenta",
             data["periodo"], data["anio"], data["mes"], data["titular"],
             data["cuenta"], data["placa"],
             data["saldo_inicial"], data["saldo_final"],
             len(data["transacciones"])))

        for tx in data["transacciones"]:
            c.execute("""INSERT INTO transacciones (extracto_id, fecha, fecha_date, descripcion, descripcion_normalizada, valor, categoria, cuota_actual, total_cuotas)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (extracto_id, tx["fecha"], tx["fecha_date"], tx["descripcion"],
                 tx["descripcion_normalizada"], tx["valor"], tx["categoria"],
                 1, 1))

        print(f"  [{extracto_id}] {fname}: {len(data['transacciones'])} tx | periodo={data['periodo']}")

    conn.commit()
    conn.close()
    print(f"\nDB: {DB_PATH}")
    print(f"Extractos: {extracto_id}")

if __name__ == "__main__":
    main()
