import re, os, shutil, sqlite3, json, csv, hashlib
from datetime import datetime, timedelta
from PyPDF2 import PdfReader, PdfWriter
import pdfplumber

# ============================================================
# CONFIG
# ============================================================
PASSWORD = "REDACTED_PWD"
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FUENTES = {
    "nequi":           os.path.join(BASE, "data", "nequi"),
    "nu":              os.path.join(BASE, "data", "nu", "pdfs"),
    "rappicard":       os.path.join(BASE, "data", "rappicard", "pdfs"),
    "tarjetas_credito": os.path.join(BASE, "data", "tarjetas_credito", "pdfs"),
}
OLD_DB = os.path.join(BASE, "data", "myfinance", "MyFinance.db")
UNLOCKED_DIR = os.path.join(BASE, "outputs", "unlocked_v2")
OUT_DB = os.path.join(BASE, "outputs", "db", "finanzas_completa.db")
OUT_JSON = os.path.join(BASE, "outputs", "db", "finanzas_completa.json")
OUT_TXT = os.path.join(BASE, "outputs", "reports", "reporte_completo.txt")
OUT_CSV_NO_CRUZ = os.path.join(BASE, "outputs", "reports", "no_cruzadas_old.csv")

MESES = {"ENE":1,"FEB":2,"MAR":3,"ABR":4,"MAY":5,"JUN":6,"JUL":7,"AGO":8,"SEP":9,"OCT":10,"NOV":11,"DIC":12,
         "ENERO":1,"FEBRERO":2,"MARZO":3,"ABRIL":4,"MAYO":5,"JUNIO":6,"JULIO":7,"AGOSTO":8,"SEPTIEMBRE":9,"OCTUBRE":10,"NOVIEMBRE":11,"DICIEMBRE":12}

# ============================================================
# HELPERS
# ============================================================
def parse_colombian_currency(s):
    if not s: return None
    s = s.strip().replace("$", "").replace(" ", "")
    if "." in s and "," in s:
        last_comma = s.rfind(",")
        last_dot = s.rfind(".")
        if last_comma > last_dot:
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try: return float(s)
    except: return None

def norm_desc(d):
    """Normaliza descripcion para matching"""
    if not d: return ""
    return re.sub(r'[^a-z0-9]', '', d.strip().lower())

def fecha_a_date(fecha_str):
    """Convierte varios formatos de fecha a date object"""
    for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"]:
        try: return datetime.strptime(fecha_str.strip(), fmt).date()
        except: pass
    # Try DD MMM YYYY (Spanish)
    for try_year in [2020,2021,2022,2023,2024,2025,2026]:
        try:
            m = re.match(r"(\d{1,2})\s+(\w+)\s+(\d{4})", fecha_str)
            if m:
                mon = MESES.get(m.group(2).upper()[:3])
                if mon: return datetime(int(m.group(3)), mon, int(m.group(1))).date()
        except: pass
        try:
            m = re.match(r"(\d{1,2})\s+(\w+)", fecha_str)
            if m:
                mon = MESES.get(m.group(2).upper()[:3])
                if mon: return datetime(try_year, mon, int(m.group(1))).date()
        except: pass
    return None

def generar_id_unico(entidad, desc, fecha, monto):
    raw = f"{entidad}|{desc}|{fecha}|{monto}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]

# ============================================================
# UNLOCK
# ============================================================
def unlock_all():
    print("Desbloqueando PDFs...")
    if os.path.exists(UNLOCKED_DIR): shutil.rmtree(UNLOCKED_DIR)
    os.makedirs(UNLOCKED_DIR)
    pdfs = []
    for nombre, dirpath in FUENTES.items():
        if not os.path.isdir(dirpath): continue
        for f in os.listdir(dirpath):
            if f.endswith(".pdf"): pdfs.append((nombre, os.path.join(dirpath, f)))
    total = len(pdfs); unlocked = 0
    for i, (fuente, path) in enumerate(pdfs, 1):
        fname = os.path.basename(path)
        try:
            reader = PdfReader(path)
            if reader.is_encrypted: reader.decrypt(PASSWORD)
            writer = PdfWriter()
            for page in reader.pages: writer.add_page(page)
            dst = os.path.join(UNLOCKED_DIR, f"{fuente}_{fname}")
            with open(dst, "wb") as fh: writer.write(fh)
            unlocked += 1
            print(f"  [{i}/{total}] [{fuente}] {fname}")
        except Exception as e:
            print(f"  [{i}/{total}] [{fuente}] {fname} -> ERROR: {e}")
    print(f"  Desbloqueados: {unlocked}/{total}")
    return unlocked

# ============================================================
# DETECT TYPE
# ============================================================
def detectar_tipo(text):
    if "Extracto de dep" in text and "Nequi" in text: return "nequi"
    if "Nu Financiera" in text or "ayuda@nu.com.co" in text: return "nu"
    if "Davivienda" in text or "RappiCard" in text: return "rappicard"
    if "CREDIT_CARD_STATEMENT" in text: return "rappicard"
    return "desconocido"

# ============================================================
# NOMBRE ARCHIVO -> PERIODO (fallback)
# ============================================================
def periodo_desde_filename(fname):
    m = re.search(r"(\d{4})(\d{2})", fname)
    if m: return f"{m.group(1)}/{m.group(2)}", int(m.group(1)), int(m.group(2))
    return None, None, None

# ============================================================
# PARSER: NEQUI
# ============================================================
def parse_nequi(filepath, fname):
    result = {"fuente": "nequi", "tipo": "deposito_bajo_monto", "transacciones": [],
              "periodo": None, "anio": None, "mes": None, "titular": None, "cuenta": None,
              "saldo_anterior": None, "total_abonos": None, "total_cargos": None,
              "saldo_actual": None, "intereses": None, "archivo": fname}
    with pdfplumber.open(filepath) as pdf:
        text = "\n".join(p.extract_text() or "" for p in pdf.pages)
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
            if abs(v) > 50_000_000: continue
            meses_str = f"{result['anio']}/{result['mes']:02d}" if result['anio'] else ""
            result["transacciones"].append({
                "fecha": txm.group(1), "fecha_date": txm.group(1),
                "descripcion": txm.group(2).strip(), "valor": v, "saldo": s,
                "entidad": "nequi", "cuenta": result["cuenta"],
                "periodo": result["periodo"], "meses_str": meses_str,
            })
        except: pass
    # Detectar prestamos
    for tx in result["transacciones"]:
        d = tx["descripcion"].upper()
        if "DESEMBOLSO" in d and "PRESTAMO" in d:
            tx["es_prestamo"] = 1; tx["tipo_prestamo"] = "desembolso"
        elif "DESEMBOLSO" in d and "CREDITO" in d:
            tx["es_prestamo"] = 1; tx["tipo_prestamo"] = "desembolso"
        elif "PAGO TOTAL DE PRESTAMO" in d:
            tx["es_prestamo"] = 1; tx["tipo_prestamo"] = "pago_total"
        elif "PAGO DEL PRESTAMO" in d or "PAGO CREDITO" in d:
            tx["es_prestamo"] = 1; tx["tipo_prestamo"] = "pago_cuota"
        elif "PAGO ADELANTADO DE CUOTA" in d or "pago adelantado de cuota" in tx["descripcion"]:
            tx["es_prestamo"] = 1; tx["tipo_prestamo"] = "pago_adelantado"
        elif d == "PAGO DE INTERESES":
            tx["es_prestamo"] = 1; tx["tipo_prestamo"] = "interes"
        else:
            tx["es_prestamo"] = 0; tx["tipo_prestamo"] = None
    return result

# ============================================================
# PARSER: NU
# ============================================================
def parse_nu(filepath, fname):
    result = {"fuente": "nu", "tipo": "tarjeta_credito", "transacciones": [],
              "periodo": None, "anio": None, "mes": None, "titular": None,
              "total_pagar": None, "pago_minimo": None, "cupo_total": None,
              "cupo_usado": None, "fecha_corte": None, "fecha_pago": None,
              "archivo": fname, "tasa_interes_mv": None, "tasa_interes_ea": None}
    with pdfplumber.open(filepath) as pdf:
        text = "\n".join(p.extract_text() or "" for p in pdf.pages)
    if re.search(r"Joel\s+Santiago\s+Neuta\s+Jaspe", text, re.IGNORECASE):
        result["titular"] = "JOEL SANTIAGO NEUTA JASPE"
    for key, alias in [("Deuda a pagar este mes", "total_pagar"),
                       ("PAGO M.NIMO", "pago_minimo"),
                       ("Tu cupo definido", "cupo_total")]:
        m = re.search(rf"{key}\s*\$?([\d.,]+)", text)
        if m: result[alias] = m.group(1)
    # Periodo
    lines = text.split("\n")
    per = None
    for i, line in enumerate(lines):
        if "periodo facturado" in line.lower() and i + 1 < len(lines):
            per = re.search(r"(\d{1,2}\s+\w+)\s*[-–—]\s*(\d{1,2}\s+\w+\s+\d{4})", lines[i+1])
            if per: break
    if not per:
        per = re.search(r"(\d{1,2}\s+\w+)\s*[-–—]\s*(\d{1,2}\s+\w+\s+\d{4})\s*$", text, re.MULTILINE)
    if per:
        result["periodo"] = f"{per.group(1)} a {per.group(2)}"
        result["anio"] = int(per.group(2).split()[-1])
    fp = re.search(r"Fecha\s*(?:l[íi]mite\s*de\s*)?pago\s+(\d+\s+\w+\s+\d{4})", text)
    if fp: result["fecha_pago"] = fp.group(1)
    fc = re.search(r"Fecha de corte\s+(\d+\s+\w+\s+\d{4})", text)
    if fc: result["fecha_corte"] = fc.group(1)
    # Extraer tasa de interes de linea de resumen
    tm = re.search(r"(\d+[,]\d+)%\s+(\d+[,]\d+)%", text)
    if tm:
        result["tasa_interes_mv"] = tm.group(1)
        result["tasa_interes_ea"] = tm.group(2)
    # Transacciones
    year = result.get("anio")
    if not year:
        ym = re.search(r"(\d{4})[/-]", filepath)
        if ym: year = int(ym.group(1))
    for line in lines:
        line = line.strip()
        m = re.match(r"(\d{2})\s+(\w+)\s+(.+?)\s+\$?([\d.,]+)\s+(\d+)\s+de\s+(\d+)\s+\$?([\d.,]+)", line)
        if m:
            day = int(m.group(1))
            mon_name = m.group(2).upper()[:3]
            desc = m.group(3).strip()
            valor = parse_colombian_currency(m.group(4))
            cuota_actual = int(m.group(5))
            total_cuotas = int(m.group(6))
            total_pagar_mes = parse_colombian_currency(m.group(7))
            if valor is None or valor <= 0 or valor >= 50_000_000: continue
            mon = MESES.get(mon_name)
            if mon is None: continue
            fy = year if year else 2026
            fd = f"{fy:04d}-{mon:02d}-{day:02d}"
            result["transacciones"].append({
                "fecha": f"{day} {m.group(2).upper()} {fy}",
                "fecha_date": fd, "descripcion": desc,
                "valor": -valor, "saldo": None,
                "entidad": "nu", "cuenta": "Nu Bank",
                "periodo": result["periodo"],
                "cuota_actual": cuota_actual, "total_cuotas": total_cuotas,
                "capital_facturado": total_pagar_mes or valor,
                "es_cuota": 1 if total_cuotas > 1 else 0,
            })
    return result

# ============================================================
# PARSER: RAPPICARD / TARJETAS CREDITO (Davivienda)
# ============================================================
def parse_rappicard(filepath, fname):
    result = {"fuente": "rappicard", "tipo": "tarjeta_credito", "transacciones": [],
              "periodo": None, "anio": None, "mes": None, "titular": None,
              "total_pagar": None, "pago_minimo": None, "cupo_total": None,
              "cupo_usado": None, "fecha_corte": None, "fecha_pago": None,
              "archivo": fname, "tasa_interes_mv": None, "tasa_interes_ea": None,
              "saldo_anterior": None, "intereses_corrientes": None}
    with pdfplumber.open(filepath) as pdf:
        text = "\n".join(p.extract_text() or "" for p in pdf.pages)
    if re.search(r"JOEL\s+SANTIAGO\s+NEUTA\s+JASPE", text):
        result["titular"] = "JOEL SANTIAGO NEUTA JASPE"
    for pattern, alias in [("Pago total", "total_pagar"),
                           ("Pago m.nimo", "pago_minimo"),
                           ("Cupo total", "cupo_total"),
                           ("Cupo utilizado", "cupo_usado")]:
        m = re.search(rf"{pattern}[:\s]*\$?\s*([\d.,]+)", text)
        if not m:
            m = re.search(rf"{pattern}\s*\n\s*\$?\s*([\d.,]+)", text)
        if m: result[alias] = m.group(1)
    # Periodo
    per_start = re.search(r"Desde\s+(\d+\s+\w+\s+\d{4})", text)
    per_end = re.search(r"Hasta\s+(\d+\s+\w+\s+\d{4})", text)
    if per_start and per_end:
        result["periodo"] = f"{per_start.group(1)} a {per_end.group(1)}"
        result["anio"] = int(per_end.group(1).split()[-1])
    # Fecha pago
    fp = re.search(r"Fecha de pago.*?(?:^|\n)\s*(\d+\s+\w+\s+\d{4})", text, re.DOTALL)
    if not fp:
        fp = re.search(r"Fecha de pago\s*\n\s*(\d+\s+\w+\s+\d{4})", text)
    if fp: result["fecha_pago"] = fp.group(1)
    # Saldo anterior e intereses
    sa = re.search(r"Saldo periodo anterior\s+\$?\s*([\d.,]+)", text)
    if sa: result["saldo_anterior"] = sa.group(1)
    ic = re.search(r"Intereses corrientes\s+\$?\s*([\d.,]+)", text)
    if ic: result["intereses_corrientes"] = ic.group(1)
    # Tasas de interes (from transaction detail footer)
    tr = re.search(r"(\d+[,]\d+)%\s+(\d+[,]\d+)%", text)
    if tr:
        result["tasa_interes_mv"] = tr.group(1)
        result["tasa_interes_ea"] = tr.group(2)
    # Transacciones
    for line in text.split("\n"):
        line = line.strip()
        m = re.match(r"(?:Virtual|Fisica|F[íi]sica|-)\s+(\d{4}-\d{2}-\d{2})\s+(.+?)\s+\$?([\d.,]+)\s+\$?([\d.,]+)\s+(\d+)\s+de\s+(\d+)", line)
        if m:
            fecha = m.group(1)
            desc = m.group(2).strip()
            valor_total = parse_colombian_currency(m.group(3))
            capital_facturado = parse_colombian_currency(m.group(4))
            cuota_actual = int(m.group(5))
            total_cuotas = int(m.group(6))
            if valor_total and valor_total > 0 and valor_total < 50_000_000:
                # Extract capital pendiente from remaining text after "de N"
                rest = line[m.end():]
                cp = re.search(r"\$?([\d.,]+)", rest)
                capital_pendiente = parse_colombian_currency(cp.group(1)) if cp else None
                # Extract rates
                tr2 = re.search(r"(\d+[,]\d+)%\s+(\d+[,]\d+)%", rest)
                tasa_mv = tr2.group(1) if tr2 else None
                tasa_ea = tr2.group(2) if tr2 else None
                result["transacciones"].append({
                    "fecha": fecha, "fecha_date": fecha,
                    "descripcion": desc, "valor": -capital_facturado,
                    "saldo": None, "entidad": "rappicard",
                    "cuenta": "RappiCard Davivienda",
                    "periodo": result["periodo"],
                    "valor_total_compra": valor_total,
                    "cuota_actual": cuota_actual, "total_cuotas": total_cuotas,
                    "capital_facturado": capital_facturado or 0,
                    "capital_pendiente": capital_pendiente or 0,
                    "es_cuota": 1 if total_cuotas > 1 else 0,
                    "tasa_mv": tasa_mv, "tasa_ea": tasa_ea,
                    "purchase_key": f"{desc.strip().upper()}|{fecha}",
                })
    return result

# ============================================================
# CLASIFICACION
# ============================================================
def clasificar(desc, valor):
    d = desc.upper().strip()
    if valor > 0:
        if "DE JUAN MANUEL GARCIA" in d: return "Sueldo"
        if "OTROS BANCOS DE" in d or "TRANSFIYA DE JOEL" in d: return "Sueldo"
        if "Pago de Intereses" in desc: return "Intereses"
        if "DESEMBOLSO" in d and ("PRESTAMO" in d or "CREDITO" in d): return "Préstamo recibido"
        if "DE GINA VANESSA" in d or "DE CAROLINA DEL PILAR" in d: return "Ingreso familiar"
        if d.startswith("DE ") or d.startswith("RECIBI POR"): return "Ingreso personas"
        if "RECARGA" in d: return "Recarga Nequi"
        if "TRANSFIYA" in d: return "Transferencia interna"
        if "REEMBOLSO" in d or "REVERSO" in d: return "Reembolso"
        return "Ingreso sin clasificar"
    if any(k in d for k in ["TIENDAS ARA","SURTITODO","D1","OXXO","EXITO","CARULLA","JUMBO","MERCADOPAGO",
                            "LA SALCHIPAPERIA","PAPA JOHNS","MC DONALD","MCDONALD","KFC","RAPPI",
                            "DIDI FOOD","HAMBURGUES","COMIDA","ALIMENTO","PANADERIA","DUNKIN","SANDWICH"]):
        return "Comida"
    if any(k in d for k in ["KOAJ","HYM","ADIDAS","NIKE","ZARA","TRENDY SHOP","DOLLARCITY"]):
        return "Ropa"
    if any(k in d for k in ["TIGO","UNE TELCO","NETFLIX","SPOTIFY","BOLD","CLARO","MOVISTAR","CASHBACK",
                            "COMCEP","COMCEL"]):
        return "Servicios"
    if any(k in d for k in ["UNAL","UNIVERSIDAD","ICETEX","MATRICULA","U. NACIONAL"]):
        return "Educacion"
    if any(k in d for k in ["FARMACIA","DROGUERIA","MEDICO","EPS","CLINICA"]):
        return "Salud"
    if any(k in d for k in ["FORTNITE","EPIC","PLAYSTATION","TUBOLETA","CINE"]):
        return "Entretenimiento"
    if any(k in d for k in ["APPLE","AMZN","AMAZON","MERCADO LIBRE","LINIO","ALIEXPRESS","GOOGLE"]):
        return "Tecnologia"
    if any(k in d for k in ["VIA MOTOS","TALLER DE","GASOLINA","MOTO","PRIMAX","ESTACION"]):
        return "Transporte"
    if any(k in d for k in ["PAGO CREDITO","PAGO ADELANTADO","PAGO TOTAL","CUOTA",
                            "PRESTAMO","DESEMBOLSO"]) and "DESEMBOLSO" not in d:
        return "Pago préstamo"
    if d.startswith("PARA "): return "Transferencia personas"
    if any(k in d for k in ["RETIRO EN","RETIRO EN CAJERO","RETIRO EN PTM","corresponsal"]):
        return "Retiro efectivo"
    if "PAGO EN QR" in d or "ENVIO CON BRE-B" in d: return "Transferencia interna"
    if "COMPRA PSE" in d or "PAGOS POR PSE" in d: return "Pago tarjeta"
    if d.startswith("COMPRA EN ") or d.startswith("COMPRA "): return "Compras general"
    if "MINISO" in d or "CASAMILAS" in d or "ESPACIO NATURA" in d: return "Compras general"
    if "LICORES" in d or "ALCOHOL" in d: return "Compras general"
    return "Sin clasificar"

# ============================================================
# PROCESAR TODO
# ============================================================
def procesar_todo():
    unlock_all()
    print("\nProcesando PDFs...")
    todos = []
    for fname in sorted(os.listdir(UNLOCKED_DIR)):
        if not fname.endswith(".pdf"): continue
        path = os.path.join(UNLOCKED_DIR, fname)
        try:
            with pdfplumber.open(path) as pdf:
                text = "\n".join(p.extract_text() or "" for p in pdf.pages)
            tipo = detectar_tipo(text)
            if tipo == "nequi": data = parse_nequi(path, fname)
            elif tipo == "nu": data = parse_nu(path, fname)
            elif tipo == "rappicard": data = parse_rappicard(path, fname)
            else: continue
            for tx in data["transacciones"]:
                tx["categoria"] = clasificar(tx["descripcion"], tx["valor"])
            todos.append(data)
            tx_count = len(data["transacciones"])
            per = data.get("periodo", "?") or "?"
            print(f"  {fname:55s} -> [{tipo:>10s}] {per:20s} ({tx_count:3d} tx)")
        except Exception as e:
            print(f"  {fname:55s} -> ERROR: {e}")
    total_tx = sum(len(d["transacciones"]) for d in todos)
    print(f"\nTotal procesados: {len(todos)} archivos, {total_tx} transacciones")
    return todos

# ============================================================
# AGRUPAR COMPRAS DIFERIDAS (RappiCard)
# ============================================================
def agrupar_compras_diferidas(todos):
    """Agrupa compras en cuotas como una sola transaccion.
       RappiCard muestra la misma compra en 2 tarjetas (Virtual/Fisica) por mes.
       Tambien aparece en rappicard_ y tarjetas_credito_ (duplicado).
       Se deduplica: mismo purchase_key + mismo periodo solo cuenta una vez."""
    compras = {}
    seen_per_periodo = set()  # (purchase_key, periodo) para deduplicar
    for data in todos:
        if data["fuente"] not in ("rappicard",): continue
        for tx in data["transacciones"]:
            pk = tx.get("purchase_key")
            if not pk: continue
            per = tx.get("periodo", "")
            dedup_key = (pk, per)
            if dedup_key in seen_per_periodo: continue  # mismo mes, misma compra → skip
            seen_per_periodo.add(dedup_key)
            if pk not in compras:
                compras[pk] = {
                    "descripcion": tx["descripcion"],
                    "fecha_original": tx["fecha"],
                    "fecha_date": tx["fecha_date"],
                    "valor_total": tx.get("valor_total_compra", abs(tx["valor"])),
                    "total_cuotas": tx["total_cuotas"],
                    "cuotas_vistas": set(),
                    "periodos_vistos": set(),
                    "max_cuota_vista": 0,
                    "ultimo_capital_pendiente": 0,
                    "ultimo_periodo": "",
                    "tasa_mv": tx.get("tasa_mv"),
                    "tasa_ea": tx.get("tasa_ea"),
                    "instalments": [],
                }
            g = compras[pk]
            g["cuotas_vistas"].add(tx["cuota_actual"])
            g["periodos_vistos"].add(per)
            if tx["cuota_actual"] > g["max_cuota_vista"]:
                g["max_cuota_vista"] = tx["cuota_actual"]
                g["ultimo_capital_pendiente"] = tx.get("capital_pendiente", 0)
                g["ultimo_periodo"] = per
            if tx.get("tasa_mv"): g["tasa_mv"] = tx["tasa_mv"]
            if tx.get("tasa_ea"): g["tasa_ea"] = tx["tasa_ea"]
            g["instalments"].append(tx)
    compras_list = []
    for pk, g in compras.items():
        g["completamente_pagado"] = 1 if g["ultimo_capital_pendiente"] == 0 else 0
        g["cuotas_observadas"] = len(g["cuotas_vistas"])
        if g["max_cuota_vista"] >= g["total_cuotas"]:
            g["completamente_pagado"] = 1
        g["purchase_id"] = generar_id_unico("rappicard", g["descripcion"], g["fecha_date"], g["valor_total"])
        compras_list.append(g)
    return compras_list


def deduplicar_rappicard_tx(todos):
    """Elimina transacciones RappiCard duplicadas GLOBALMENTE (misma compra+mismo periodo entre rappicard y tarjetas_credito)"""
    seen = set()
    for data in todos:
        if data["fuente"] != "rappicard": continue
        uniq = []
        for tx in data["transacciones"]:
            pk = tx.get("purchase_key", "")
            per = tx.get("periodo", "")
            key = (pk, per, tx.get("cuota_actual"))
            if key not in seen:
                seen.add(key)
                uniq.append(tx)
        data["transacciones"] = uniq
    return todos


# ============================================================
# IDENTIFICAR PRESTAMOS NEQUI
# ============================================================
def identificar_prestamos(todos):
    """Agrupa desembolsos y pagos de prestamos de Nequi"""
    prestamos = []
    current_id = 0
    # Recopilar todas las tx de prestamo
    loan_txs = []
    for data in todos:
        if data["fuente"] != "nequi": continue
        for tx in data["transacciones"]:
            if tx.get("es_prestamo"):
                loan_txs.append(tx)
    # Identificar desembolsos
    desembolsos = [tx for tx in loan_txs if tx.get("tipo_prestamo") == "desembolso"]
    for d in desembolsos:
        current_id += 1
        pid = f"NEQUI-LOAN-{current_id:03d}"
        monto = d["valor"]
        prestamo = {
            "id": pid,
            "fecha_desembolso": d["fecha"],
            "monto_principal": monto,
            "pagos": [],
            "intereses": [],
            "total_pagado": 0,
            "interes_pagado": 0,
            "estado": "activo",
        }
        d["prestamo_id"] = pid
        # Buscar pagos e intereses DESPUES del desembolso
        d_date = fecha_a_date(d["fecha_date"]) or datetime.strptime(d["fecha"][:10], "%d/%m/%Y") if "/" in d["fecha"] else datetime.strptime(d["fecha"][:10], "%Y-%m-%d")
        if isinstance(d_date, datetime): d_date = d_date.date()
        for tx in loan_txs:
            if tx is d: continue
            tx_date = fecha_a_date(tx.get("fecha_date") or tx["fecha"])
            if tx_date and tx_date >= d_date:
                tp = tx.get("tipo_prestamo")
                if tp in ("pago_cuota", "pago_total", "pago_adelantado"):
                    prestamo["pagos"].append(tx)
                    prestamo["total_pagado"] += abs(tx["valor"])
                    tx["prestamo_id"] = pid
                elif tp == "interes":
                    prestamo["intereses"].append(tx)
                    prestamo["interes_pagado"] += tx["valor"]
                    tx["prestamo_id"] = pid
        # Calcular interes
        if prestamo["monto_principal"] > 0:
            exceso = prestamo["total_pagado"] - prestamo["monto_principal"]
            prestamo["interes_calculado"] = max(0, exceso)
            prestamo["tasa_interes"] = (prestamo["interes_calculado"] / prestamo["monto_principal"]) * 100 if prestamo["monto_principal"] > 0 else 0
        else:
            prestamo["interes_calculado"] = 0
            prestamo["tasa_interes"] = 0
        prestamo["estado"] = "pagado" if prestamo["total_pagado"] >= prestamo["monto_principal"] else "activo"
        prestamos.append(prestamo)
    return prestamos

# ============================================================
# CALCULAR INTERESES TARJETAS
# ============================================================
def calcular_intereses_tarjetas(todos):
    """Calcula tasa de interes efectiva desde extractos"""
    cards = []
    for data in todos:
        if data["fuente"] not in ("nu", "rappicard"): continue
        saldo_ant = parse_colombian_currency(data.get("saldo_anterior"))
        intereses = parse_colombian_currency(data.get("intereses_corrientes"))
        tasa_mv = data.get("tasa_interes_mv")
        tasa_ea = data.get("tasa_interes_ea")
        card_info = {
            "entidad": data["fuente"],
            "periodo": data.get("periodo"),
            "saldo_anterior": saldo_ant,
            "intereses_corrientes": intereses,
            "tasa_interes_mv": tasa_mv,
            "tasa_interes_ea": tasa_ea,
        }
        if saldo_ant and intereses and saldo_ant > 0:
            card_info["tasa_interes_mv_calculada"] = round((intereses / saldo_ant) * 100, 4)
        else:
            card_info["tasa_interes_mv_calculada"] = None
        cards.append(card_info)
    return cards

# ============================================================
# CARGAR BD ANTIGUA
# ============================================================
def cargar_bd_antigua():
    print("\nCargando base de datos antigua...")
    if not os.path.exists(OLD_DB):
        print(f"  AVISO: {OLD_DB} no encontrada")
        return []
    conn_old = sqlite3.connect(OLD_DB)
    conn_old.row_factory = sqlite3.Row
    cur = conn_old.cursor()
    cur.execute("""
        SELECT t.uid, t.type, t.amountInDefaultCurrency, t.date, t.comment,
               COALESCE(c.title, 'Sin categoria') as category_name
        FROM "transaction" t
        LEFT JOIN sync_link sl ON sl.entityUid = t.uid AND sl.entityType='Transaction' AND sl.otherType='Category'
        LEFT JOIN category c ON sl.otherUid = c.uid
        WHERE t.isRemoved=0
        ORDER BY t.date
    """)
    rows = cur.fetchall()
    old_txs = []
    for r in rows:
        old_txs.append({
            "uid": r["uid"],
            "type": r["type"],
            "amount": r["amountInDefaultCurrency"],
            "date": r["date"],
            "comment": r["comment"] or "",
            "category": r["category_name"],
        })
    conn_old.close()
    print(f"  Cargadas {len(old_txs)} transacciones antiguas")
    return old_txs

# ============================================================
# CRUZAR DATOS
# ============================================================
def cruzar_datos(new_txs, old_txs):
    """Cruza transacciones nuevas (PDF) con antiguas (app).
       Criterios: descripcion normalizada, fecha ±3 dias,
       monto tolerancia ±20%, categoria similar."""
    print("\nCruzando transacciones...")
    matched_pairs = []  # (new_tx, old_tx, score)
    unmatched_new = []
    unmatched_old = list(old_txs)  # copia, iremos quitando
    
    # Index old by normalized description prefix
    old_by_desc = {}
    for ot in old_txs:
        nd = norm_desc(ot["comment"])[:25]
        if nd:
            old_by_desc.setdefault(nd, []).append(ot)
    
    matched_old_uids = set()
    
    for nt in new_txs:
        best_match = None
        best_score = 0
        nd_new = norm_desc(nt["descripcion"])[:25]
        nt_date = fecha_a_date(nt.get("fecha_date") or nt["fecha"])
        nt_amount = abs(nt["valor"])
        
        # Try to find match in old by normalized desc
        candidates = []
        # Search by description prefix match (first 15 chars)
        nd_prefix = nd_new[:15]
        for nd_old, ots in old_by_desc.items():
            if nd_prefix in nd_old or nd_old[:15] in nd_prefix:
                candidates.extend(ots)
            # Also try word overlap
            words_new = set(nd_new.split())
            words_old = set(nd_old.split())
            if len(words_new & words_old) >= 2:
                candidates.extend(ots)
        
        # Deduplicate candidates
        seen = set()
        unique_candidates = []
        for c in candidates:
            if c["uid"] not in seen:
                seen.add(c["uid"])
                unique_candidates.append(c)
        
        for ot in unique_candidates:
            if ot["uid"] in matched_old_uids: continue
            score = 0
            # 1. Description match
            nd_old = norm_desc(ot["comment"])[:25]
            desc_sim = len(set(nd_new) & set(nd_old)) / max(len(set(nd_new) | set(nd_old)), 1)
            score += desc_sim * 30  # max 30 points
            
            # Word overlap
            words_new_set = set(nd_new.split())
            words_old_set = set(nd_old.split())
            if len(words_new_set) > 0 and len(words_old_set) > 0:
                word_overlap = len(words_new_set & words_old_set) / max(len(words_new_set | words_old_set), 1)
                score += word_overlap * 20
            
            # 2. Date match
            ot_date = fecha_a_date(ot["date"])
            if nt_date and ot_date:
                diff = abs((nt_date - ot_date).days)
                if diff <= 1: score += 25
                elif diff <= 3: score += 15
                elif diff <= 7: score += 5
            
            # 3. Amount match (old amounts are rounded to thousands)
            old_amt = ot["amount"]
            if nt_amount > 0 and old_amt > 0:
                # Check if old amount is within 20% of new amount
                ratio = nt_amount / old_amt
                if 0.8 <= ratio <= 1.25:
                    score += 20
                # Also check if new amount rounds to old amount (new / old ≈ 1 with tolerance)
                if abs(nt_amount - old_amt) / max(nt_amount, old_amt) <= 0.3:
                    score += 10
            
            # 4. Category compatibility
            cat_new = nt.get("categoria", "").upper()
            cat_old = ot.get("category", "").upper()
            # Map new categories to old
            cat_map = {
                "COMIDA": ["ALIMENTACIÓN", "ALIMENTACION"],
                "SALUD": ["SALUD"],
                "EDUCACION": ["EDUCACIÓN", "EDUCACION"],
                "TRANSPORTE": ["TRANSPORTE"],
                "SERVICIOS": ["SERVICIOS DIGITALES", "RECIBOS"],
                "ROPA": ["ROPA"],
                "ENTRETENIMIENTO": ["SALIDAS", "RUTINA"],
                "TECNOLOGIA": ["SERVICIOS DIGITALES"],
                "SUELDO": ["SALARIO"],
                "INGRESO PERSONAS": ["OTROS"],
                "INGRESO FAMILIAR": ["FAMILIA"],
                "PAGO PRéSTAMO": ["PRESTAMOS A MI"],
                "PRéSTAMO RECIBIDO": ["PRESTAMOS QUE HAGO"],
            }
            for nc, ocs in cat_map.items():
                if nc in cat_new:
                    for oc in ocs:
                        if oc in cat_old:
                            score += 15
                            break
            if cat_new[:5] in cat_old or cat_old[:5] in cat_new:
                score += 5
            
            if score > best_score and score >= 40:
                best_score = score
                best_match = ot
        
        if best_match:
            matched_pairs.append((nt, best_match, best_score))
            matched_old_uids.add(best_match["uid"])
        else:
            unmatched_new.append(nt)
    
    # Old unmatched
    unmatched_old = [ot for ot in old_txs if ot["uid"] not in matched_old_uids]
    
    print(f"  Cruzadas: {len(matched_pairs)}")
    print(f"  No cruzadas (nuevas): {len(unmatched_new)}")
    print(f"  No cruzadas (antiguas): {len(unmatched_old)}")
    return matched_pairs, unmatched_new, unmatched_old

# ============================================================
# CONSTRUIR DB UNIFICADA
# ============================================================
def construir_db(todos, compras_diferidas, prestamos, intereses_tarjetas,
                 matched_pairs, unmatched_new, unmatched_old):
    print("\nConstruyendo base de datos unificada...")
    if os.path.exists(OUT_DB): os.remove(OUT_DB)
    conn = sqlite3.connect(OUT_DB)
    conn.execute("PRAGMA journal_mode=WAL")
    c = conn.cursor()
    
    c.executescript("""
        CREATE TABLE extractos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            archivo TEXT, fuente TEXT, tipo TEXT,
            periodo TEXT, anio INTEGER, mes INTEGER,
            titular TEXT, cuenta TEXT,
            total_pagar REAL, pago_minimo REAL, cupo_total REAL,
            saldo_anterior REAL, total_abonos REAL, total_cargos REAL, saldo_actual REAL,
            fecha_corte TEXT, fecha_pago TEXT,
            num_transacciones INTEGER,
            tasa_interes_mv REAL, tasa_interes_ea REAL,
            intereses_corrientes REAL
        );
        CREATE TABLE transacciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            extracto_id INTEGER REFERENCES extractos(id),
            fecha TEXT, fecha_date TEXT,
            descripcion TEXT, valor REAL, saldo REAL,
            entidad TEXT, cuenta TEXT, periodo TEXT,
            categoria TEXT, es_ingreso INTEGER,
            es_recurrente INTEGER DEFAULT 0,
            es_cuota INTEGER DEFAULT 0,
            total_cuotas INTEGER, cuota_actual INTEGER,
            capital_facturado REAL, capital_pendiente REAL,
            valor_total_compra REAL,
            purchase_group_id TEXT,
            es_prestamo INTEGER DEFAULT 0,
            tipo_prestamo TEXT, prestamo_id TEXT,
            matched_old_uid TEXT, match_score REAL,
            purchase_key TEXT
        );
        CREATE TABLE compras_diferidas (
            purchase_id TEXT PRIMARY KEY,
            descripcion TEXT, fecha_original TEXT,
            valor_total REAL, total_cuotas INTEGER,
            cuotas_observadas INTEGER, cuotas_vistas TEXT,
            capital_pendiente_actual REAL,
            completamente_pagado INTEGER DEFAULT 0,
            entidad TEXT,
            tasa_interes_mv REAL, tasa_interes_ea REAL
        );
        CREATE TABLE prestamos (
            id TEXT PRIMARY KEY,
            fecha_desembolso TEXT, monto_principal REAL,
            total_pagado REAL, interes_pagado REAL,
            interes_calculado REAL, tasa_interes REAL,
            num_pagos INTEGER, estado TEXT
        );
        CREATE TABLE intereses_tarjetas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entidad TEXT, periodo TEXT,
            saldo_anterior REAL, intereses_corrientes REAL,
            tasa_mv_declarada REAL, tasa_ea_declarada REAL,
            tasa_mv_calculada REAL
        );
        CREATE TABLE cruce (
            old_uid TEXT, tx_id INTEGER, match_score REAL,
            FOREIGN KEY (tx_id) REFERENCES transacciones(id)
        );
        CREATE TABLE no_cruzadas_old (
            uid TEXT PRIMARY KEY, tipo TEXT, monto INTEGER,
            fecha TEXT, descripcion TEXT, categoria TEXT
        );
        CREATE INDEX idx_tx_fecha ON transacciones(fecha_date);
        CREATE INDEX idx_tx_categoria ON transacciones(categoria);
        CREATE INDEX idx_tx_entidad ON transacciones(entidad);
        CREATE INDEX idx_tx_purchase_key ON transacciones(purchase_key);
    """)
    
    # Insert extractos and transacciones
    for data in todos:
        cu = data.get("cuenta")
        c.execute("""
            INSERT INTO extractos
            (archivo, fuente, tipo, periodo, anio, mes, titular, cuenta,
             total_pagar, pago_minimo, cupo_total,
             saldo_anterior, total_abonos, total_cargos, saldo_actual,
             fecha_corte, fecha_pago, num_transacciones,
             tasa_interes_mv, tasa_interes_ea, intereses_corrientes)
            VALUES (?,?,?,?,?,?,?,?, ?,?,?, ?,?,?,?, ?,?,?, ?,?,?)
        """, (
            data["archivo"], data["fuente"], data["tipo"],
            data.get("periodo"), data.get("anio"), data.get("mes"),
            data.get("titular"), cu,
            parse_colombian_currency(data.get("total_pagar")),
            parse_colombian_currency(data.get("pago_minimo")),
            parse_colombian_currency(data.get("cupo_total")),
            parse_colombian_currency(data.get("saldo_anterior")),
            parse_colombian_currency(data.get("total_abonos")),
            parse_colombian_currency(data.get("total_cargos")),
            parse_colombian_currency(data.get("saldo_actual")),
            data.get("fecha_corte"), data.get("fecha_pago"),
            len(data["transacciones"]),
            parse_colombian_currency(data.get("tasa_interes_mv")),
            parse_colombian_currency(data.get("tasa_interes_ea")),
            parse_colombian_currency(data.get("intereses_corrientes")),
        ))
        eid = c.lastrowid
        for tx in data["transacciones"]:
            es_ing = 1 if tx["valor"] > 0 else 0
            c.execute("""
                INSERT INTO transacciones
                (extracto_id, fecha, fecha_date, descripcion, valor, saldo,
                 entidad, cuenta, periodo, categoria, es_ingreso,
                 es_cuota, total_cuotas, cuota_actual,
                 capital_facturado, capital_pendiente,
                 valor_total_compra, purchase_group_id,
                 es_prestamo, tipo_prestamo, prestamo_id,
                 purchase_key)
                VALUES (?,?,?,?,?,?, ?,?,?,?,?,
                        ?,?,?, ?,?,?,?, ?,?,?, ?)
            """, (eid, tx["fecha"], tx.get("fecha_date"), tx["descripcion"],
                  tx["valor"], tx.get("saldo"),
                  tx["entidad"], tx.get("cuenta"), tx.get("periodo"),
                  tx["categoria"], es_ing,
                  tx.get("es_cuota", 0), tx.get("total_cuotas"), tx.get("cuota_actual"),
                  tx.get("capital_facturado"), tx.get("capital_pendiente"),
                  tx.get("valor_total_compra"), tx.get("purchase_id"),
                  tx.get("es_prestamo", 0), tx.get("tipo_prestamo"), tx.get("prestamo_id"),
                  tx.get("purchase_key")))
    conn.commit()
    
    # Insert purchase groups
    for g in compras_diferidas:
        c.execute("""
            INSERT OR REPLACE INTO compras_diferidas
            (purchase_id, descripcion, fecha_original, valor_total, total_cuotas,
             cuotas_observadas, cuotas_vistas, capital_pendiente_actual,
             completamente_pagado, entidad,
             tasa_interes_mv, tasa_interes_ea)
            VALUES (?,?,?,?,?, ?,?,?, ?,?, ?,?)
        """, (g["purchase_id"], g["descripcion"], g["fecha_date"],
              g["valor_total"], g["total_cuotas"],
              g["cuotas_observadas"],
              ",".join(str(c) for c in sorted(g["cuotas_vistas"])),
              g["ultimo_capital_pendiente"],
              g["completamente_pagado"], "rappicard",
              g.get("tasa_mv"), g.get("tasa_ea")))
    conn.commit()
    
    # Insert loans
    for p in prestamos:
        c.execute("""
            INSERT OR REPLACE INTO prestamos
            (id, fecha_desembolso, monto_principal, total_pagado,
             interes_pagado, interes_calculado, tasa_interes,
             num_pagos, estado)
            VALUES (?,?,?,?, ?,?,?, ?,?)
        """, (p["id"], p["fecha_desembolso"], p["monto_principal"],
              p["total_pagado"], p["interes_pagado"],
              p.get("interes_calculado"), p.get("tasa_interes"),
              len(p["pagos"]), p["estado"]))
    conn.commit()
    
    # Insert interest rates
    for ci in intereses_tarjetas:
        c.execute("""
            INSERT INTO intereses_tarjetas
            (entidad, periodo, saldo_anterior, intereses_corrientes,
             tasa_mv_declarada, tasa_ea_declarada, tasa_mv_calculada)
            VALUES (?,?,?,?, ?,?,?)
        """, (ci["entidad"], ci["periodo"], ci["saldo_anterior"],
              ci["intereses_corrientes"],
              ci.get("tasa_interes_mv"), ci.get("tasa_interes_ea"),
              ci.get("tasa_interes_mv_calculada")))
    conn.commit()
    
    # Build tx_id lookup for matched pairs
    # We need to get the id of each inserted transaction
    c.execute("""
        SELECT t.id, t.fecha_date, t.descripcion, t.valor, t.entidad
        FROM transacciones t ORDER BY t.id
    """)
    all_new_tx_rows = c.fetchall()
    
    # Match by date+description+amount+entidad
    for nt, ot, score in matched_pairs:
        for row in all_new_tx_rows:
            row_date = row[1] or ""
            nt_date = nt.get("fecha_date") or nt["fecha"][:10]
            if (row_date[:10] == nt_date[:10] and
                norm_desc(row[2])[:15] == norm_desc(nt["descripcion"])[:15] and
                abs(abs(row[3]) - abs(nt["valor"])) / max(abs(nt["valor"]), 1) < 0.1 and
                row[4] == nt["entidad"]):
                # Update transaction with matched info
                c.execute("UPDATE transacciones SET matched_old_uid=?, match_score=? WHERE id=?",
                         (ot["uid"], round(score, 1), row[0]))
                c.execute("INSERT INTO cruce (old_uid, tx_id, match_score) VALUES (?,?,?)",
                         (ot["uid"], row[0], round(score, 1)))
                break
    
    conn.commit()
    
    # Insert unmatched old transactions
    for ot in unmatched_old:
        c.execute("""
            INSERT OR REPLACE INTO no_cruzadas_old
            (uid, tipo, monto, fecha, descripcion, categoria)
            VALUES (?,?,?,?,?,?)
        """, (ot["uid"], ot["type"], ot["amount"], ot["date"],
              ot["comment"], ot["category"]))
    conn.commit()
    
    conn.close()
    print(f"  Base de datos creada: {OUT_DB}")

# ============================================================
# EXPORTAR REPORTES
# ============================================================
def exportar_reportes(todos, compras_diferidas, prestamos, intereses_tarjetas,
                      matched_pairs, unmatched_old):
    lines = []
    def L(s=""): lines.append(s)
    
    L("=" * 90)
    L("  REPORTE FINANCIERO COMPLETO")
    L("  Titular: JOEL SANTIAGO NEUTA JASPE")
    L(f"  Fecha: {datetime.now().strftime('%d/%m/%Y')}")
    L("=" * 90)
    
    # Totals
    total_ing = sum(t["valor"] for d in todos for t in d["transacciones"] if t["valor"] > 0)
    total_egr = sum(abs(t["valor"]) for d in todos for t in d["transacciones"] if t["valor"] < 0)
    total_tx = sum(len(d["transacciones"]) for d in todos)
    L(f"\nTotal transacciones: {total_tx:,}")
    L(f"Total ingresos:      ${total_ing:,.2f}")
    L(f"Total egresos:       ${total_egr:,.2f}")
    L(f"Balance:             ${total_ing - total_egr:,.2f}")
    
    # By entity
    entities = {}
    for d in todos:
        for t in d["transacciones"]:
            ent = t["entidad"]
            entities.setdefault(ent, {"tx": 0, "ing": 0, "egr": 0})
            entities[ent]["tx"] += 1
            if t["valor"] > 0: entities[ent]["ing"] += t["valor"]
            else: entities[ent]["egr"] += abs(t["valor"])
    L("\n" + "-" * 90)
    L("POR ENTIDAD")
    L(f"{'Entidad':<20s} {'Extractos':>10s} {'Tx':>12s} {'Ingresos':>15s} {'Egresos':>15s}")
    L("-" * 72)
    for ent in ["nequi", "nu", "rappicard"]:
        edata = entities.get(ent, {"tx": 0, "ing": 0, "egr": 0})
        extractos = sum(1 for d in todos if d["fuente"] == ent)
        L(f"{ent:<20s} {extractos:>10d} {edata['tx']:>12d} ${edata['ing']:>12,.2f} ${edata['egr']:>12,.2f}")
    
    # Credit card interest rates
    L("\n" + "-" * 90)
    L("INTERESES TARJETAS DE CREDITO")
    L(f"{'Entidad':<12s} {'Periodo':<25s} {'Saldo Ant':>12s} {'Intereses':>12s} {'Tasa MV':>10s} {'Tasa EA':>10s} {'Tasa Calc':>10s}")
    L("-" * 90)
    for ci in intereses_tarjetas:
        L(f"{ci['entidad']:<12s} {str(ci['periodo']):<25s} "
          f"${ci['saldo_anterior'] or 0:>10,.2f} ${ci['intereses_corrientes'] or 0:>10,.2f} "
          f"{str(ci['tasa_interes_mv'] or '?'):>10s} {str(ci['tasa_interes_ea'] or '?'):>10s} "
          f"{str(ci.get('tasa_interes_mv_calculada', '') or '?'):>10s}")
    
    # Compras diferidas
    L("\n" + "-" * 90)
    L("COMPRAS DIFERIDAS (CUOTAS)")
    L(f"{'Descripcion':<35s} {'Valor':>12s} {'Cuotas':>8s} {'Vistas':>8s} {'Pendiente':>12s} {'Pagado':>8s} {'Tasa EA':>10s}")
    L("-" * 90)
    for g in sorted(compras_diferidas, key=lambda x: -x["valor_total"]):
        pagado = "SI" if g["completamente_pagado"] else "NO"
        L(f"{g['descripcion'][:34]:<35s} ${g['valor_total']:>10,.0f} "
          f"{g['total_cuotas']:>3d}/{g['total_cuotas']:<3d} {g['cuotas_observadas']:>3d}/{g['total_cuotas']:<3d} "
          f"${g['ultimo_capital_pendiente']:>9,.0f} {pagado:>8s} "
          f"{g.get('tasa_ea', '?'):>10s}")
    
    # Prestamos
    L("\n" + "-" * 90)
    L("PRESTAMOS NEQUI")
    L(f"{'ID':<16s} {'Fecha':<12s} {'Principal':>12s} {'Pagado':>12s} {'Interes':>10s} {'Tasa':>8s} {'Estado':>10s}")
    L("-" * 90)
    for p in prestamos:
        L(f"{p['id']:<16s} {p['fecha_desembolso']:<12s} ${p['monto_principal']:>9,.0f} "
          f"${p['total_pagado']:>9,.0f} ${p.get('interes_calculado', 0):>8,.0f} "
          f"{p.get('tasa_interes', 0):>7.2f}% {p['estado']:>10s}")
    
    # Cruce
    L("\n" + "-" * 90)
    L("CRUCE CON BASE DE DATOS ANTIGUA")
    L(f"Transacciones cruzadas exitosamente: {len(matched_pairs)}")
    L(f"Transacciones antiguas no cruzadas: {len(unmatched_old)}")
    L(f"\nTransacciones no cruzadas (revisar manualmente):")
    L(f"{'Fecha':<12s} {'Monto':>10s} {'Categoria':<20s} {'Descripcion':<50s}")
    L("-" * 92)
    for ot in sorted(unmatched_old, key=lambda x: x["date"])[:50]:
        L(f"{ot['date']:<12s} ${ot['amount']:>8,d} {ot['category'][:19]:<20s} {ot['comment'][:49]:<50s}")
    if len(unmatched_old) > 50:
        L(f"  ... y {len(unmatched_old) - 50} mas (ver CSV)")
    
    # Monthly evolution
    L("\n" + "-" * 90)
    L("EVOLUCION MENSUAL - NEQUI")
    monthly = {}
    for d in todos:
        if d["fuente"] != "nequi": continue
        per = d.get("periodo")
        if not per: continue
        monthly.setdefault(per, {"ing": 0, "egr": 0, "tx": 0})
        for t in d["transacciones"]:
            monthly[per]["tx"] += 1
            if t["valor"] > 0: monthly[per]["ing"] += t["valor"]
            else: monthly[per]["egr"] += abs(t["valor"])
    L(f"{'Periodo':<12s} {'Ingresos':>12s} {'Gastos':>12s} {'Balance':>12s} {'Tx':>6s}")
    L("-" * 54)
    for per in sorted(monthly.keys()):
        m = monthly[per]
        bal = m["ing"] - m["egr"]
        L(f"{per:<12s} ${m['ing']:>9,.2f} ${m['egr']:>9,.2f} ${bal:>9,.2f} {m['tx']:>6d}")
    
    L("\n" + "=" * 90)
    L("FIN DEL REPORTE")
    
    with open(OUT_TXT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Reporte guardado: {OUT_TXT}")
    
    # Export unmatched old to CSV
    with open(OUT_CSV_NO_CRUZ, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["uid", "tipo", "monto", "fecha", "descripcion", "categoria"])
        for ot in sorted(unmatched_old, key=lambda x: x["date"]):
            w.writerow([ot["uid"], ot["type"], ot["amount"], ot["date"], ot["comment"], ot["category"]])
    print(f"No cruzadas exportadas: {OUT_CSV_NO_CRUZ}")

# ============================================================
# JSON EXPORT
# ============================================================
def exportar_json(todos, compras_diferidas, prestamos, matched_pairs, unmatched_old):
    result = {
        "metadata": {
            "titular": "JOEL SANTIAGO NEUTA JASPE",
            "fecha": datetime.now().isoformat(),
            "total_transacciones": sum(len(d["transacciones"]) for d in todos),
            "total_archivos": len(todos),
        },
        "transacciones": [],
        "compras_diferidas": [{
            "purchase_id": g["purchase_id"],
            "descripcion": g["descripcion"],
            "fecha_original": g["fecha_date"],
            "valor_total": g["valor_total"],
            "total_cuotas": g["total_cuotas"],
            "cuotas_observadas": g["cuotas_observadas"],
            "completamente_pagado": bool(g["completamente_pagado"]),
            "tasa_interes_ea": g.get("tasa_ea"),
        } for g in compras_diferidas],
        "prestamos": [{
            "id": p["id"],
            "fecha_desembolso": p["fecha_desembolso"],
            "monto_principal": p["monto_principal"],
            "total_pagado": p["total_pagado"],
            "tasa_interes": p.get("tasa_interes"),
            "estado": p["estado"],
        } for p in prestamos],
        "cruce": {
            "cruzadas": len(matched_pairs),
            "no_cruzadas_old": len(unmatched_old),
        },
    }
    for d in todos:
        for tx in d["transacciones"]:
            entry = {
                "fecha": tx["fecha"], "fecha_date": tx.get("fecha_date"),
                "descripcion": tx["descripcion"], "valor": tx["valor"],
                "entidad": tx["entidad"], "categoria": tx["categoria"],
                "es_cuota": tx.get("es_cuota", 0),
                "total_cuotas": tx.get("total_cuotas"),
                "cuota_actual": tx.get("cuota_actual"),
                "es_prestamo": tx.get("es_prestamo", 0),
                "tipo_prestamo": tx.get("tipo_prestamo"),
                "prestamo_id": tx.get("prestamo_id"),
                "periodo": tx.get("periodo"),
            }
            if tx.get("matched_old_uid"):
                entry["matched"] = True
                entry["match_score"] = tx.get("match_score")
            result["transacciones"].append(entry)
    
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"JSON exportado: {OUT_JSON}")

# ============================================================
# MAIN
# ============================================================
def main():
    print("=" * 60)
    print("  ANALISIS UNIFICADO DE FINANZAS v2")
    print("  Incluye: cuotas, prestamos, intereses, cruce BD antigua")
    print("=" * 60)
    
    # 1. Procesar todos los PDFs
    todos = procesar_todo()
    if not todos:
        print("No se procesaron archivos. Abortando.")
        return
    
    # 1b. Deduplicar RappiCard (misma compra+mismo periodo en rappicard y tarjetas_credito)
    print("\nDeduplicando transacciones RappiCard...")
    before = sum(len(d["transacciones"]) for d in todos if d["fuente"] == "rappicard")
    todos = deduplicar_rappicard_tx(todos)
    after = sum(len(d["transacciones"]) for d in todos if d["fuente"] == "rappicard")
    print(f"  RappiCard tx: {before} -> {after} (eliminadas {before - after} duplicadas)")
    
    # 2. Agrupar compras diferidas
    print("\nAnalizando compras diferidas...")
    compras_diferidas = agrupar_compras_diferidas(todos)
    print(f"  Compras en cuotas identificadas: {len(compras_diferidas)}")
    
    # 3. Identificar prestamos Nequi
    print("\nIdentificando prestamos Nequi...")
    prestamos = identificar_prestamos(todos)
    print(f"  Prestamos encontrados: {len(prestamos)}")
    for p in prestamos:
        print(f"    {p['id']}: ${p['monto_principal']:,.0f} - {p['estado']} "
              f"(pagado=${p['total_pagado']:,.0f}, interes={p.get('tasa_interes', 0):.2f}%)")
    
    # 4. Calcular intereses tarjetas
    print("\nCalculando intereses de tarjetas...")
    intereses_tarjetas = calcular_intereses_tarjetas(todos)
    for ci in intereses_tarjetas:
        if ci.get("tasa_interes_mv_calculada"):
            print(f"  {ci['entidad']} {ci['periodo']}: MV={ci['tasa_interes_mv_calculada']:.2f}%")
    
    # 5. Cargar BD antigua
    old_txs = cargar_bd_antigua()
    
    # 6. Cruzar datos
    new_txs_flat = [tx for d in todos for tx in d["transacciones"]]
    matched_pairs, unmatched_new, unmatched_old = cruzar_datos(new_txs_flat, old_txs)
    
    # 7. Construir DB unificada
    construir_db(todos, compras_diferidas, prestamos, intereses_tarjetas,
                 matched_pairs, unmatched_new, unmatched_old)
    
    # 8. Reportes
    exportar_reportes(todos, compras_diferidas, prestamos, intereses_tarjetas,
                      matched_pairs, unmatched_old)
    
    # 9. JSON
    exportar_json(todos, compras_diferidas, prestamos, matched_pairs, unmatched_old)
    
    print("\n" + "=" * 60)
    print("  PROCESO COMPLETADO")
    print(f"  DB: {OUT_DB}")
    print(f"  JSON: {OUT_JSON}")
    print(f"  TXT: {OUT_TXT}")
    print("=" * 60)

if __name__ == "__main__":
    main()
