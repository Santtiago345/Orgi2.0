"""
Analisis COMPLETO de extractos Nu Bank
========================================
Parsea PDFs de Nu, genera data/nu/nu_finanzas.db
"""
import os, re, sqlite3
import pdfplumber
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF_DIR = os.path.join(BASE, "data", "nu")
DB_PATH = os.path.join(PDF_DIR, "nu_finanzas.db")

def parse_colombian_currency(s):
    if not s: return None
    s = s.strip().replace("$", "").replace(" ", "")
    if "." in s and "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try: return float(s)
    except: return None

MESES_MAP = {"ENE":1,"FEB":2,"MAR":3,"ABR":4,"MAY":5,"JUN":6,"JUL":7,"AGO":8,"SEP":9,"OCT":10,"NOV":11,"DIC":12,
             "ENERO":1,"FEBRERO":2,"MARZO":3,"ABRIL":4,"MAYO":5,"JUNIO":6,"JULIO":7,"AGOSTO":8,"SEPTIEMBRE":9,"OCTUBRE":10,"NOVIEMBRE":11,"DICIEMBRE":12}

def clasificar_nu(desc):
    d = desc.upper().strip()
    if any(k in d for k in ['TIENDAS ARA','D1','OXXO','EXITO','CARULLA','JUMBO','MERCADO','ALIMENTO','PANADERIA','COMIDA']):
        return 'Comida'
    if any(k in d for k in ['DOLLARCITY','TRENDY SHOP','MINISO','CASAMILAS','ESPACIO NATURA','FALABELLA']):
        return 'Compras general'
    if any(k in d for k in ['NETFLIX','SPOTIFY','BOLD']):
        return 'Servicios'
    if any(k in d for k in ['UNIVERSIDAD','MATRICULA']):
        return 'Educacion'
    if any(k in d for k in ['PRIMAX','GASOLINA','TRANSPORTE','CABIFY','UBER']):
        return 'Transporte'
    if any(k in d for k in ['FARMACIA','DROGUERIA','MEDICO','EPS','CLINICA']):
        return 'Salud'
    if any(k in d for k in ['INTERES','CUOTA DE MANEJO','AVANCE']):
        return 'Cargos financieros'
    return 'Sin clasificar'

def parse_nu_pdf(filepath):
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
        partes = per.group(2).split()
        mes_nombre = partes[1].upper()
        mes_num = MESES_MAP.get(mes_nombre)
        if mes_num:
            result["mes"] = mes_num

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
            })

    return result

def main():
    print("=" * 60)
    print("ANALISIS DE EXTRACTOS NU")
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
            id INTEGER PRIMARY KEY, archivo TEXT, periodo TEXT, anio INTEGER, mes INTEGER,
            titular TEXT, total_pagar REAL, pago_minimo REAL, cupo_total REAL,
            saldo_anterior REAL, fecha_corte TEXT, fecha_pago TEXT,
            interes_corriente REAL, tasa_mensual REAL, tasa_anual_ea REAL,
            es_refinanciacion INTEGER DEFAULT 0, num_transacciones INTEGER
        );
        CREATE TABLE IF NOT EXISTS transacciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT, extracto_id INTEGER,
            fecha TEXT, fecha_date TEXT, descripcion TEXT, descripcion_normalizada TEXT,
            valor REAL, categoria TEXT, cuota_actual INTEGER DEFAULT 1,
            total_cuotas INTEGER DEFAULT 1,
            FOREIGN KEY (extracto_id) REFERENCES extractos(id)
        );
    """)
    conn.commit()

    extracto_id = 0
    for fname in sorted(pdfs):
        path = os.path.join(PDF_DIR, fname)
        try:
            data = parse_nu_pdf(path)
            extracto_id += 1

            total_pagar = parse_colombian_currency(data.get("total_pagar"))
            pago_minimo = parse_colombian_currency(data.get("pago_minimo"))
            cupo_total = parse_colombian_currency(data.get("cupo_total"))
            saldo_anterior = parse_colombian_currency(data.get("saldo_anterior"))
            interes_corriente = parse_colombian_currency(data.get("interes_corriente"))
            tasa_mensual = parse_colombian_currency(data.get("tasa_mensual"))
            tasa_anual_ea = parse_colombian_currency(data.get("tasa_anual_ea"))

            c.execute("""INSERT INTO extractos (id, archivo, periodo, anio, mes, titular,
                total_pagar, pago_minimo, cupo_total, saldo_anterior,
                fecha_corte, fecha_pago, interes_corriente, tasa_mensual, tasa_anual_ea, num_transacciones)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (extracto_id, fname, data["periodo"], data["anio"], data["mes"], data["titular"],
                 total_pagar, pago_minimo, cupo_total, saldo_anterior,
                 data.get("fecha_corte"), data.get("fecha_pago"),
                 interes_corriente, tasa_mensual, tasa_anual_ea,
                 len(data["transacciones"])))

            for tx in data["transacciones"]:
                cat = clasificar_nu(tx["descripcion"])
                c.execute("""INSERT INTO transacciones (extracto_id, fecha, fecha_date, descripcion, descripcion_normalizada, valor, categoria, cuota_actual, total_cuotas)
                    VALUES (?,?,?,?,?,?,?,?,?)""",
                    (extracto_id, tx["fecha"], tx["fecha_date"], tx["descripcion"],
                     re.sub(r'[^A-Z0-9\s]', '', tx["descripcion"].upper()).strip(),
                     tx["valor"], cat,
                     tx.get("cuota_actual", 1), tx.get("total_cuotas", 1)))

            print(f"  [{extracto_id}] {fname}: {len(data['transacciones'])} tx | periodo={data['periodo']}")
        except Exception as e:
            print(f"  ERROR en {fname}: {e}")
            import traceback
            traceback.print_exc()

    conn.commit()
    conn.close()
    print(f"\nDB: {DB_PATH}")
    print(f"Extractos: {extracto_id}")

if __name__ == "__main__":
    main()
