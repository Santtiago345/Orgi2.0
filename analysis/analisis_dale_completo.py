"""
Analisis COMPLETO de extractos Dale
Parea PDFs, clasifica transacciones, genera data/dale/dale_finanzas.db
"""
import os, re, sqlite3, hashlib
import pdfplumber

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF_DIR = os.path.join(BASE, "data", "dale")
DB_PATH = os.path.join(PDF_DIR, "dale_finanzas.db")

MESES_LARGO = {
    "enero":1,"febrero":2,"marzo":3,"abril":4,"mayo":5,"junio":6,
    "julio":7,"agosto":8,"septiembre":9,"octubre":10,"noviembre":11,"diciembre":12
}

def parse_dale_currency(s):
    if not s: return None
    s = s.strip().replace("$", "").replace("+", "").replace(" ", "")
    negativo = s.endswith("-")
    if negativo: s = s[:-1]
    if "." in s:
        parts = s.rsplit(".", 1)
        if len(parts) == 2 and len(parts[1]) <= 2 and len(parts[1]) > 0:
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(".", "")
    elif "," in s:
        parts = s.rsplit(",", 1)
        if len(parts) == 2 and len(parts[1]) == 2:
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    try:
        v = float(s)
        return -v if negativo else v
    except:
        return None

CLASIFICACION = [
    (["ABONO", "MONEDERO", "BOLSILLO"], "Ingreso recurrente"),
    (["RETIRO ATM", "CAJERO"], "Retiro efectivo"),
    (["PSE", "COMPRAS", "PAGOS", "COMPRA"], "Compra PSE"),
    (["TRANSFIYA", "TRANSFERENCIA", "ENVIAR", "TRANS CTA", "TRANS CUENTA"], "Transferencia a personas"),
    (["DISPERSION", "DEBITO"], "Compras general"),
]

def clasificar_dale(desc):
    d = desc.upper().strip()
    for keywords, cat in CLASIFICACION:
        if any(kw in d for kw in keywords):
            return cat
    return "Sin clasificar"

def parse_dale_pdf(filepath):
    text = ""
    with pdfplumber.open(filepath) as pdf:
        for p in pdf.pages:
            t = p.extract_text()
            if t: text += t + "\n"

    result = {
        "fuente": "dale",
        "tipo": "cuenta",
        "titular": None,
        "deposito": None,
        "periodo": None,
        "anio": None,
        "mes": None,
        "saldo_inicial": None,
        "saldo_final": None,
        "total_abonos": None,
        "total_debitos": None,
        "transacciones": [],
    }

    tm = re.search(r"(Joel|JOEL)\s+(Santiago|SANTIAGO)\s+(Neuta|NEUTA)\s+(Jaspe|JASPE)", text)
    if tm: result["titular"] = "JOEL SANTIAGO NEUTA JASPE"

    dm = re.search(r"No\.?\s*de\s*dep[oó]sito[:\s]*(\d+)", text, re.IGNORECASE)
    if dm: result["deposito"] = dm.group(1)

    pm = re.search(r"Fecha de extracto[:\s]*(\w+)\s+(\d{4})", text)
    if pm:
        mes = MESES_LARGO.get(pm.group(1).lower())
        anio = int(pm.group(2))
        if mes:
            result["anio"] = anio
            result["mes"] = mes
            result["periodo"] = f"{anio}/{mes:02d}"

    sm = re.search(r"Saldo inicial\s*\$?\s*([\d.,\-]+)", text, re.IGNORECASE)
    if sm: result["saldo_inicial"] = parse_dale_currency(sm.group(1))
    sf = re.search(r"Saldo final\s*\$?\s*([\d.,\-]+)", text, re.IGNORECASE)
    if sf: result["saldo_final"] = parse_dale_currency(sf.group(1))
    ta = re.search(r"Total abonos?\s*\$?\s*([\d.,]+)", text, re.IGNORECASE)
    if ta: result["total_abonos"] = parse_dale_currency(ta.group(1))
    td = re.search(r"Total d[eé]bitos?\s*\$?\s*([\d.,]+)", text, re.IGNORECASE)
    if td: result["total_debitos"] = parse_dale_currency(td.group(1))

    for line in text.split("\n"):
        line = line.strip()
        m = re.match(r"^(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})\s+(.+)", line)
        if not m:
            continue
        fecha = m.group(1)
        resto = m.group(3).strip()

        is_abono = "+" in resto
        is_debito = bool(re.search(r'\$\d[\d.,]+\s*-\s', resto))

        tokens = resto.split()
        desc_parts = []
        i = 0
        while i < len(tokens):
            t = tokens[i]
            if t in ("+", "-"):
                i += 1
                continue
            if t.startswith("$"):
                break
            desc_parts.append(t)
            i += 1

        descripcion = " ".join(desc_parts).strip()

        valores = []
        while i < len(tokens):
            t = tokens[i]
            if t in ("+", "-"):
                i += 1
                continue
            if t.startswith("$"):
                valores.append(t)
            i += 1

        if len(valores) == 0 or not descripcion:
            continue

        valor = parse_dale_currency(valores[0])
        if valor is None:
            continue

        if is_abono:
            valor = abs(valor)
        elif is_debito:
            valor = -abs(valor)
        else:
            continue

        result["transacciones"].append({
            "fecha": fecha,
            "fecha_date": fecha,
            "descripcion": descripcion[:100],
            "descripcion_normalizada": re.sub(r'[^A-Z0-9\s]', '', descripcion.upper()).strip(),
            "valor": valor,
            "categoria": clasificar_dale(descripcion),
            "cuota_actual": 1,
            "total_cuotas": 1,
        })

    return result

def crear_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS extractos (
            id INTEGER PRIMARY KEY,
            archivo TEXT,
            hash TEXT,
            fuente TEXT,
            tipo TEXT,
            periodo TEXT,
            anio INTEGER,
            mes INTEGER,
            titular TEXT,
            deposito TEXT,
            saldo_inicial REAL,
            saldo_final REAL,
            total_abonos REAL,
            total_debitos REAL,
            num_transacciones INTEGER
        );
        CREATE TABLE IF NOT EXISTS transacciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            extracto_id INTEGER,
            fecha TEXT,
            fecha_date TEXT,
            descripcion TEXT,
            descripcion_normalizada TEXT,
            valor REAL,
            categoria TEXT,
            cuota_actual INTEGER DEFAULT 1,
            total_cuotas INTEGER DEFAULT 1,
            FOREIGN KEY (extracto_id) REFERENCES extractos(id)
        );
    """)
    conn.commit()
    return conn

def main():
    print("=" * 60)
    print("ANALISIS DE EXTRACTOS DALE")
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

    conn = crear_db()
    c = conn.cursor()
    extracto_id = 0

    for fname in sorted(pdfs):
        path = os.path.join(PDF_DIR, fname)
        # Calcular hash del PDF
        file_hash = ""
        try:
            with open(path, "rb") as f:
                file_hash = hashlib.md5(f.read()).hexdigest()
        except:
            pass
        try:
            data = parse_dale_pdf(path)
            extracto_id += 1
            c.execute("""INSERT INTO extractos (id, archivo, hash, fuente, tipo, periodo, anio, mes, titular, deposito, saldo_inicial, saldo_final, total_abonos, total_debitos, num_transacciones)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (extracto_id, fname, file_hash, "dale", "cuenta",
                 data["periodo"], data["anio"], data["mes"], data["titular"],
                 data["deposito"], data["saldo_inicial"], data["saldo_final"],
                 data["total_abonos"], data["total_debitos"],
                 len(data["transacciones"])))

            for tx in data["transacciones"]:
                c.execute("""INSERT INTO transacciones (extracto_id, fecha, fecha_date, descripcion, descripcion_normalizada, valor, categoria, cuota_actual, total_cuotas)
                    VALUES (?,?,?,?,?,?,?,?,?)""",
                    (extracto_id, tx["fecha"], tx["fecha_date"], tx["descripcion"],
                     tx["descripcion_normalizada"], tx["valor"], tx["categoria"],
                     tx["cuota_actual"], tx["total_cuotas"]))

            print(f"  [{extracto_id}] {fname}: {len(data['transacciones'])} transacciones | periodo={data['periodo']}")
        except Exception as e:
            print(f"  ERROR en {fname}: {e}")
            import traceback
            traceback.print_exc()

    conn.commit()
    conn.close()
    print(f"\nDB generada: {DB_PATH}")
    print(f"Extractos procesados: {extracto_id}")

if __name__ == "__main__":
    main()
