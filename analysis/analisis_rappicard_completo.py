"""
Analisis COMPLETO de extractos RappiCard
==========================================
Parsea PDFs de RappiCard, genera data/rappicard/rappicard_finanzas.db
"""
import os, re, sqlite3, hashlib
import pdfplumber
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF_DIR = os.path.join(BASE, "data", "rappicard")
DB_PATH = os.path.join(PDF_DIR, "rappicard_finanzas.db")

def parse_colombian_currency(s):
    if not s: return None
    s = s.strip().replace("$", "").replace(" ", "")
    if "." in s and "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try: return float(s)
    except: return None

def clasificar_rappicard(desc):
    d = desc.upper().strip()
    if any(k in d for k in ['TIENDAS ARA','SURTITODO','D1','OXXO','EXITO',
                            'CARULLA','JUMBO','MERCADOPAGO','LA SALCHIPAPERIA',
                            'PAPA JOHNS','MC DONALD','MCDONALD','KFC','RAPPI',
                            'DIDI FOOD','HAMBURGUES','COMIDA','ALIMENTO',
                            'PANADERIA','DUNKIN','SANDWICH','STARBUCKS',
                            'PRAGA','SUBS WAY','SUBWAY','PIZZA','CARNES',
                            'FRUVER','MULTIAHORRO','MERCADO']):
        return 'Comida'
    if any(k in d for k in ['KOAJ','HYM','ADIDAS','NIKE','ZARA','TRENDY SHOP',
                            'DOLLARCITY','FALABELLA','CUIDADO CON EL PERRO']):
        return 'Ropa'
    if any(k in d for k in ['TIGO','UNE TELCO','NETFLIX','SPOTIFY','BOLD',
                            'CLARO','MOVISTAR','CASHBACK']):
        return 'Servicios'
    if any(k in d for k in ['UNAL','UNIVERSIDAD','ICETEX','MATRICULA','U. NACIONAL']):
        return 'Educacion'
    if any(k in d for k in ['FARMACIA','DROGUERIA','MEDICO','EPS','CLINICA',
                            'FARMASHOP','FARMEDICAL','DENTAL']):
        return 'Salud'
    if any(k in d for k in ['FORTNITE','EPIC','PLAYSTATION','TUBOLETA','CINE',
                            'BOOMERANG','CERVEZA','LICORES']):
        return 'Entretenimiento'
    if any(k in d for k in ['APPLE','AMZN','AMAZON','MERCADO LIBRE','LINIO',
                            'ALIEXPRESS','LOGITECH','HUAWEI']):
        return 'Tecnologia'
    if any(k in d for k in ['VIA MOTOS','TALLER DE','GASOLINA','MOTO',
                            'PRIMAX','ESTACION','CABIFY','UBER','TAXI','TRANSPORTE']):
        return 'Transporte'
    if any(k in d for k in ['HOTEL','AIRBNB','VUELO','VIAJE','DESPEGAR']):
        return 'Viajes'
    if any(k in d for k in ['MINISO','CASAMILAS','ESPACIO NATURA','ZONA DE MODA']):
        return 'Compras general'
    if any(k in d for k in ['AJUSTE COMPRA','INTERES','CUOTA DE MANEJO']):
        return 'Cargos financieros'
    if d.startswith('COMPRA EN ') or d.startswith('COMPRA '):
        return 'Compras general'
    return 'Sin clasificar'

def parse_rappicard_pdf(filepath):
    result = {"fuente": "rappicard", "tipo": "tarjeta_credito", "transacciones": [],
              "periodo": None, "anio": None, "mes": None, "titular": None,
              "total_pagar": None, "pago_minimo": None, "cupo_total": None,
              "cupo_usado": None, "saldo_anterior": None, "saldo_actual": None,
              "total_cargos": None, "total_abonos": None,
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

    meses = {"ENE":1,"FEB":2,"MAR":3,"ABR":4,"MAY":5,"JUN":6,"JUL":7,"AGO":8,"SEP":9,"OCT":10,"NOV":11,"DIC":12,
             "ENERO":1,"FEBRERO":2,"MARZO":3,"ABRIL":4,"MAYO":5,"JUNIO":6,"JULIO":7,"AGOSTO":8,"SEPTIEMBRE":9,"OCTUBRE":10,"NOVIEMBRE":11,"DICIEMBRE":12}

    if per_start:
        partes = per_start.group(1).split()
        if len(partes) >= 3:
            mes_nombre = partes[1].upper()
            mes_num = meses.get(mes_nombre)
            if mes_num:
                result["mes"] = mes_num
                result["anio"] = int(partes[2])

    fp = re.search(r"Fecha de pago.*?(?:^|\n)\s*(\d+\s+\w+\s+\d{4})", text, re.DOTALL)
    if not fp:
        fp = re.search(r"Fecha de pago\s*\n\s*(\d+\s+\w+\s+\d{4})", text)
    if fp: result["fecha_pago"] = fp.group(1)

    lines = text.split("\n")
    for line in lines:
        line = line.strip()
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
                })

    total_cargos = sum(abs(tx["valor"]) for tx in result["transacciones"] if tx["valor"] < 0)
    total_abonos = sum(tx["valor"] for tx in result["transacciones"] if tx["valor"] > 0)
    result["total_cargos"] = total_cargos if total_cargos else None
    result["total_abonos"] = total_abonos if total_abonos else None

    saldo_anterior_val = parse_colombian_currency(result.get("saldo_anterior"))
    if saldo_anterior_val and result["total_cargos"] and result["total_abonos"] is not None:
        result["saldo_actual"] = saldo_anterior_val + result["total_cargos"] - (result["total_abonos"] or 0)
    elif result["total_cargos"]:
        cupo = parse_colombian_currency(result.get("cupo_usado"))
        if cupo:
            result["saldo_actual"] = cupo

    return result

def main():
    print("=" * 60)
    print("ANALISIS DE EXTRACTOS RAPPICARD")
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
            id INTEGER PRIMARY KEY, archivo TEXT, hash TEXT, periodo TEXT, anio INTEGER, mes INTEGER,
            titular TEXT, total_pagar REAL, pago_minimo REAL, cupo_total REAL,
            saldo_anterior REAL, saldo_actual REAL,
            total_cargos REAL, total_abonos REAL,
            fecha_corte TEXT, fecha_pago TEXT,
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
        # Calcular hash del PDF
        file_hash = ""
        try:
            with open(path, "rb") as f:
                file_hash = hashlib.md5(f.read()).hexdigest()
        except:
            pass
        try:
            data = parse_rappicard_pdf(path)
            if len(data["transacciones"]) == 0:
                print(f"  [SKIP] {fname}: sin transacciones")
                continue
            extracto_id += 1

            total_pagar = parse_colombian_currency(data.get("total_pagar"))
            pago_minimo = parse_colombian_currency(data.get("pago_minimo"))
            cupo_total = parse_colombian_currency(data.get("cupo_total"))
            saldo_anterior = parse_colombian_currency(data.get("saldo_anterior"))
            interes_corriente = parse_colombian_currency(data.get("interes_corriente"))
            tasa_mensual = parse_colombian_currency(data.get("tasa_mensual"))
            tasa_anual_ea = parse_colombian_currency(data.get("tasa_anual_ea"))

            saldo_actual_raw = data.get("saldo_actual")
            if isinstance(saldo_actual_raw, (int, float)):
                saldo_actual_val = saldo_actual_raw
            else:
                saldo_actual_val = parse_colombian_currency(saldo_actual_raw)
            total_cargos = data.get("total_cargos")
            total_abonos = data.get("total_abonos")

            c.execute("""INSERT INTO extractos (id, archivo, hash, periodo, anio, mes, titular,
                total_pagar, pago_minimo, cupo_total, saldo_anterior, saldo_actual,
                total_cargos, total_abonos,
                fecha_corte, fecha_pago, interes_corriente, tasa_mensual, tasa_anual_ea, num_transacciones)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (extracto_id, fname, file_hash, data["periodo"], data["anio"], data["mes"], data["titular"],
                 total_pagar, pago_minimo, cupo_total, saldo_anterior, saldo_actual_val,
                 total_cargos, total_abonos,
                 data.get("fecha_corte"), data.get("fecha_pago"),
                 interes_corriente, tasa_mensual, tasa_anual_ea,
                 len(data["transacciones"])))

            for tx in data["transacciones"]:
                cat = clasificar_rappicard(tx["descripcion"])
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
