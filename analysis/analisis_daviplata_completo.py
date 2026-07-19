"""
Analisis COMPLETO de extractos Daviplata
===========================================
- Parsea PDFs de Daviplata
- Clasifica cada transaccion
- Genera data/daviplata/daviplata_finanzas.db
"""
import os, re, json, sqlite3, hashlib
import pdfplumber
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF_DIR = os.path.join(BASE, "data", "daviplata")
DB_PATH = os.path.join(PDF_DIR, "daviplata_finanzas.db")

MESES_LARGO = {
    "enero":1,"febrero":2,"marzo":3,"abril":4,"mayo":5,"junio":6,
    "julio":7,"agosto":8,"septiembre":9,"octubre":10,"noviembre":11,"diciembre":12
}

def parse_colombian_currency(s):
    if not s: return None
    s = s.strip().replace("$", "").replace(" ", "")
    if "." in s and "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try: return float(s)
    except: return None
INGRESO_KW = ["ABONO", "NOTA CREDITO", "ACEPTAR PLATA", "TRANS CTA", "CUENTA-MONEDE"]


CLASIFICACION = [
    (["ABONO", "NOTA CREDITO", "ACEPTAR PLATA", "TRANS CTA", "CUENTA-MONEDE"], "Ingreso recurrente"),
    (["RETIRO ATM"], "Retiro efectivo"),
    (["PSE COMPRAS", "PAGOS", "COMPRA"], "Compra PSE"),
    (["TRANSFERENCIA", "ENVIAR PLATA", "TRANSFIYA", "PASO PLATA", "BRE-B"], "Transferencia a personas"),
    (["DISPERSION"], "Compras general"),
]

def clasificar_daviplata(desc):
    d = desc.upper().strip()
    for keywords, cat in CLASIFICACION:
        if any(kw in d for kw in keywords):
            return cat
    return "Sin clasificar"

def es_ingreso_daviplata(desc):
    d = desc.upper().strip()
    return any(kw in d for kw in INGRESO_KW)

def parse_valor_con_espacios(valor_str):
    s = valor_str.replace(" ", "").replace(",", "")
    try: return float(s)
    except: return None

def parse_daviplata_pdf(filepath):
    text = ""
    with pdfplumber.open(filepath) as pdf:
        for p in pdf.pages:
            t = p.extract_text()
            if t: text += t + "\n"

    result = {
        "fuente": "daviplata",
        "tipo": "cuenta",
        "titular": None,
        "periodo": None,
        "anio": None,
        "mes": None,
        "saldo": None,
        "fecha_saldo": None,
        "transacciones": [],
    }

    tm = re.search(r"JOEL SANTIAGO NEUTA JASPE", text, re.IGNORECASE)
    if tm: result["titular"] = "JOEL SANTIAGO NEUTA JASPE"

    pm = re.search(r"Periodo del extracto entre:\s*(\w+)\s+(\d{4})\s*[-–—]\s*(\w+)\s+(\d{4})", text, re.IGNORECASE)
    if pm:
        mes_ini = MESES_LARGO.get(pm.group(1).lower())
        anio_ini = int(pm.group(2))
        mes_fin = MESES_LARGO.get(pm.group(3).lower())
        anio_fin = int(pm.group(4))
        if mes_ini and mes_fin:
            result["anio"] = anio_fin
            result["mes"] = mes_fin
            result["periodo"] = f"{anio_ini}/{mes_ini:02d} - {anio_fin}/{mes_fin:02d}"

    sm = re.search(r"Saldo DaviPlata\s*\$?\s*([\d.,]+)", text)
    if sm: result["saldo"] = parse_colombian_currency(sm.group(1))

    fm = re.search(r"Fecha del Saldo\s+(\d{2}/\d{2}/\d{4})", text)
    if fm: result["fecha_saldo"] = fm.group(1)

    with pdfplumber.open(filepath) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    if not row or len(row) < 5:
                        continue
                    fecha = (row[0] or "").strip()
                    if not re.match(r"^\d{4}-\d{2}-\d{2}$", fecha):
                        continue
                    valor_str = (row[1] or "").strip()
                    descripcion = (row[4] or "").strip()
                    if not valor_str or not descripcion:
                        continue

                    valor = parse_valor_con_espacios(valor_str)
                    if valor is None:
                        continue

                    es_ing = es_ingreso_daviplata(descripcion)
                    valor_final = abs(valor) if es_ing else -abs(valor)

                    result["transacciones"].append({
                        "fecha": fecha,
                        "fecha_date": fecha,
                        "descripcion": descripcion[:100],
                        "descripcion_normalizada": re.sub(r'[^A-Z0-9\s]', '', descripcion.upper()).strip(),
                        "valor": valor_final,
                        "categoria": clasificar_daviplata(descripcion),
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
            saldo_actual REAL,
            num_transacciones INTEGER,
            fecha_saldo TEXT
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
    print("ANALISIS DE EXTRACTOS DAVIPLATA")
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
            data = parse_daviplata_pdf(path)
            if len(data["transacciones"]) == 0:
                print(f"  [SKIP] {fname}: sin transacciones")
                continue
            extracto_id += 1
            c.execute("""INSERT INTO extractos (id, archivo, hash, fuente, tipo, periodo, anio, mes, titular, saldo_actual, num_transacciones)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (extracto_id, fname, file_hash, "daviplata", "cuenta",
                 data["periodo"], data["anio"], data["mes"], data["titular"],
                 data["saldo"], len(data["transacciones"])))

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
