"""
Analisis COMPLETO de extractos Nequi + Clasificacion + DB SQLite
=================================================================
- Extrae datos de todos los PDFs
- Clasifica cada transaccion por categoria
- Detecta patrones recurrentes (sueldo, pagos periodicos, etc.)
- Guarda en SQLite para usar en la app de finanzas
"""
import os
import hashlib
import re
import json
import shutil
import sqlite3
import pdfplumber
from pypdf import PdfReader, PdfWriter
from datetime import datetime, date
from collections import defaultdict, Counter

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF_DIR = os.path.join(BASE, "PDFs_Gmail NEQUI")
UNLOCKED_DIR = os.path.join(PDF_DIR, "unlocked")
PASSWORD = os.environ.get("PDF_PASSWORD", "")
DB_PATH = os.path.join(PDF_DIR, "nequi_finanzas.db")
JSON_PATH = os.path.join(PDF_DIR, "nequi_transacciones_completo.json")

MESES = ["Enero","Febrero","Marzo","Abril","Mayo","Junio",
         "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]

# ============================================================
# CLASIFICACION POR PALABRAS CLAVE
# ============================================================
def clasificar_transaccion(desc, valor):
    desc_up = desc.upper()
    es_ingreso = not desc_up.startswith("PARA ") and valor > 0

    # --- INGRESOS ---
    if es_ingreso:
        # Sueldo / ingresos laborales periodicos
        if any(k in desc_up for k in ["DE JUAN MANUEL GARCIA"]):
            return "Sueldo"
        if any(k in desc_up for k in ["OTROS BANCOS DE UNAL", "OTROS BANCOS DE BOGOTA", "OTROS BANCOS DE"]):
            return "Sueldo"
        if "TRANSFIYA DE JOEL" in desc_up:
            return "Transferencia interna"
        if "DESEMBOLSO" in desc_up and ("PRESTAMO" in desc_up or "CREDITO" in desc_up):
            return "Préstamo recibido"
        if "RECARGA" in desc_up and ("NEQUI PSE" in desc_up or "DESDE" in desc_up or "EN" in desc_up):
            return "Recarga Nequi"
        if "RECIBI POR BRE-B" in desc_up:
            return "Transferencia interna"
        if "RECIBI POR BRE-B DE: JOEL" in desc_up or "RECIBI POR BRE-B DE: OSCAR" in desc_up:
            return "Transferencia interna"
        if "PAGO DE INTERESES" in desc_up or "Pago de Intereses" in desc:
            return "Intereses Nequi"
        if "REVERSO" in desc_up or "REEMBOLSO" in desc_up:
            return "Reembolso"
        if "DE GINA VANESSA JASPE" in desc_up:
            return "Ingreso familiar"
        if "DE CAROLINA DEL PILAR JASPE" in desc_up or "DE KAREM MILENA NEUTA" in desc_up:
            return "Ingreso familiar"
        if "DE LAURA CAMILA TIQUE" in desc_up:
            return "Ingreso recurrente"
        if "DE ANDRES DAVID DIAZ" in desc_up or "DE JHON CAMILO TRUJILLO" in desc_up:
            return "Ingreso recurrente"
        if desc_up.startswith("DE "):
            return "Ingreso de personas"
        return "Ingreso sin clasificar"

    # --- GASTOS ---
    # Comida: supermercados y restaurantes
    if any(k in desc_up for k in ["TIENDAS ARA", "SURTITODO", "D1", "OXXO", "EXITO",
                                    "CARULLA", "JUMBO", "MERCADOPAGO", "MERCADO",
                                    "LA SALCHIPAPERIA", "PAPA JOHNS", "MC DONALD",
                                    "MCDONALD", "KFC", "RAPPI", "DIDI FOOD",
                                    "HAMBURGUES", "COMIDA", "ALIMENTO"]):
        return "Comida"
    # Ropa
    if any(k in desc_up for k in ["KOAJ", "HYM", "ADIDAS", "NIKE", "PUMA",
                                    "ZARA", "FALABELLA", "LA LEY"]):
        return "Ropa"
    # Transporte / vehiculos
    if any(k in desc_up for k in ["VIA MOTOS", "TALLER DE MOTOS", "GASOLINA", "MOTO",
                                    "VEHICULO", "SOAT"]):
        return "Transporte"
    # Servicios publicos / facturas
    if any(k in desc_up for k in ["TIGO FACTURAS", "UNE TELCO", "NETFLIX", "SPOTIFY",
                                    "BOLD", "CLARO", "MOVISTAR"]):
        return "Servicios"
    # Educacion
    if any(k in desc_up for k in ["UNAL", "UNIVERSIDAD NACIONAL", "U. NACIONAL",
                                    "ICETEX", "MATRICULA", "UNIVERSIDAD"]):
        return "Educacion"
    # Salud
    if any(k in desc_up for k in ["FARMACIA", "DROGUERIA", "MEDICO", "EPS", "ODONTO",
                                    "CLINICA", "HOSPITAL", "LABORATORIO"]):
        return "Salud"
    # Entretenimiento
    if any(k in desc_up for k in ["FORTNITE", "EPIC GAMES", "PLAYSTATION", "XBOX",
                                    "STEAM", "CINE", "TUBOLETA"]):
        return "Entretenimiento"
    # Tecnologia
    if any(k in desc_up for k in ["APPLE", "AMZN", "AMAZON", "MERCADO LIBRE",
                                    "LINIO", "ALIEXPRESS"]):
        return "Tecnologia"
    # Vivienda
    if any(k in desc_up for k in ["ARRENDAMIENTO", "ARRIENDO", "ADMINISTRACION",
                                    "CONDOMINIO"]):
        return "Vivienda"
    # Pago prestamo / credito
    if any(k in desc_up for k in ["PAGO CREDITO", "PAGO ADELANTADO", "PAGO TOTAL",
                                    "CUOTA", "PRESTAMO"]):
        if "DESEMBOLSO" not in desc_up:
            return "Pago préstamo"
    # Transferencias a personas (Para ...)
    if desc_up.startswith("PARA "):
        return "Transferencia a personas"
    # Retiros
    if any(k in desc_up for k in ["RETIRO EN", "RETIRO EN CAJERO", "RETIRO EN PTM",
                                    "RETIRO EN CORRESPONSAL", "Recarga en corresponsales",
                                    "Retiro en corresponsales"]):
        return "Retiro efectivo"
    # Pago QR
    if "PAGO EN QR" in desc_up or "ENVIO CON BRE-B" in desc_up:
        return "Transferencia interna"
    # Compras PSE
    if "COMPRA PSE" in desc_up:
        return "Compra PSE"
    # Compras generales
    if desc_up.startswith("COMPRA EN ") or desc_up.startswith("COMPRA "):
        return "Compras general"
    if "TARJETA NEQUI" in desc_up:
        return "Compra tarjeta Nequi"

    return "Sin clasificar"


# ============================================================
# EXTRACCION DE PDF
# ============================================================
def unlock_pdfs():
    print("Desbloqueando PDFs...")
    if os.path.exists(UNLOCKED_DIR):
        shutil.rmtree(UNLOCKED_DIR)
    os.makedirs(UNLOCKED_DIR)
    pdfs = [f for f in os.listdir(PDF_DIR) if f.endswith(".pdf") and f != "unlocked"]
    ok = 0
    for f in pdfs:
        src = os.path.join(PDF_DIR, f)
        try:
            reader = PdfReader(src)
            if reader.is_encrypted:
                reader.decrypt(PASSWORD)
            writer = PdfWriter()
            for page in reader.pages:
                writer.add_page(page)
            dst = os.path.join(UNLOCKED_DIR, f)
            with open(dst, "wb") as fh:
                writer.write(fh)
            ok += 1
        except Exception as e:
            print(f"  ERROR {f}: {e}")
    print(f"  Desbloqueados: {ok}")
    return ok


def parse_pdf(filepath):
    """Extrae datos completos de un PDF Nequi"""
    result = {
        "archivo": os.path.basename(filepath),
        "periodo": None, "anio": None, "mes": None,
        "titular": None, "cuenta": None,
        "saldo_anterior": None, "total_abonos": None, "total_cargos": None,
        "saldo_actual": None, "saldo_promedio": None, "intereses": None,
        "transacciones": [],
    }

    with pdfplumber.open(filepath) as pdf:
        full_text = ""
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                full_text += t + "\n"

    # Periodo
    pm = re.search(r"per[ií]odo\s+de:\s*(\d{4})/(\d{2})/\d{2}\s+a\s+(\d{4})/(\d{2})/(\d{2})", full_text)
    if pm:
        result["anio"] = int(pm.group(1))
        result["mes"] = int(pm.group(2))
        result["periodo"] = f"{result['anio']}/{result['mes']:02d}"
    else:
        nm = re.search(r"(\d{4})(\d{2})", os.path.basename(filepath))
        if nm:
            result["anio"] = int(nm.group(1))
            result["mes"] = int(nm.group(2))
            result["periodo"] = f"{result['anio']}/{result['mes']:02d}"

    nm2 = re.search(r"Extracto.*\n\s*(.+?)(?:\n|$)", full_text)
    if nm2:
        result["titular"] = nm2.group(1).strip()

    am = re.search(r"N[uú]mero\s+de\s+dep[óo]sito[^:]*:\s*(\d+)", full_text)
    if am:
        result["cuenta"] = am.group(1)

    def extract_val(text, key):
        p = re.compile(rf"{re.escape(key)}\s*\$?([\d.,]+)")
        m = p.search(text)
        return m.group(1) if m else None

    result["saldo_anterior"] = extract_val(full_text, "Saldo anterior")
    result["total_abonos"] = extract_val(full_text, "Total abonos")
    result["total_cargos"] = extract_val(full_text, "Total cargos")
    result["saldo_actual"] = extract_val(full_text, "Saldo actual")
    result["saldo_promedio"] = extract_val(full_text, "Saldo promedio")
    result["intereses"] = extract_val(full_text, "intereses pagados")

        # Transacciones
    in_tx = False
    for line in full_text.split("\n"):
        if "Fecha del movimiento" in line:
            in_tx = True
            continue
        if not in_tx:
            continue
        if "Los dep" in line or "Puedes consultar" in line:
            break
        line = line.strip()
        if not line:
            continue
        # Formato: "31/05/2026  COMPRA EN BOGOTA 70  $-21,800.00  $1,242,628.44"
        txm = re.match(
            r"(\d{2}/\d{2}/\d{4})\s+(.+?)\s+\$?(-?[\d,]+\.\d{2})\s+\$?(-?[\d,]+\.\d{2})\s*$",
            line
        )
        if not txm:
            continue
        fecha_str = txm.group(1)
        desc = txm.group(2).strip()
        val_str = txm.group(3).replace(",", "")
        saldo_str = txm.group(4).replace(",", "")
        try:
            valor = float(val_str)
            saldo = float(saldo_str)
        except ValueError:
            continue
        # Sanity check: rechazar valores irrealistas (> $50M)
        if abs(valor) > 50_000_000 or abs(saldo) > 50_000_000:
            continue
        result["transacciones"].append({
            "fecha": fecha_str,
            "descripcion": desc,
            "valor": valor,
            "saldo": saldo,
        })

    return result


# ============================================================
# BASE DE DATOS SQLite
# ============================================================
def crear_db(conn):
    conn.executescript("""
        PRAGMA journal_mode=WAL;

        CREATE TABLE IF NOT EXISTS extractos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            archivo TEXT UNIQUE,
            hash TEXT,
            periodo TEXT,
            anio INTEGER,
            mes INTEGER,
            titular TEXT,
            cuenta TEXT,
            saldo_anterior REAL,
            total_abonos REAL,
            total_cargos REAL,
            saldo_actual REAL,
            saldo_promedio REAL,
            intereses REAL,
            num_transacciones INTEGER
        );

        CREATE TABLE IF NOT EXISTS transacciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            extracto_id INTEGER REFERENCES extractos(id),
            fecha TEXT,
            fecha_date DATE,
            descripcion TEXT,
            descripcion_normalizada TEXT,
            contraparte TEXT,
            valor REAL,
            es_ingreso INTEGER,
            saldo REAL,
            categoria TEXT,
            subcategoria TEXT,
            es_recurrente INTEGER DEFAULT 0,
            grupo_recurrencia TEXT
        );

        CREATE TABLE IF NOT EXISTS categorias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE,
            tipo TEXT,
            descripcion TEXT
        );

        CREATE TABLE IF NOT EXISTS patrones_recurrentes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT,
            descripcion TEXT,
            contraparte TEXT,
            monto REAL,
            frecuencia TEXT,
            num_ocurrencias INTEGER,
            primer_ocurrencia TEXT,
            ultima_ocurrencia TEXT,
            meses_activo INTEGER,
            confianza REAL
        );

        CREATE TABLE IF NOT EXISTS contrapartes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE,
            tipo TEXT,
            categoria_principal TEXT,
            total_transacciones INTEGER,
            total_ingresos REAL,
            total_egresos REAL,
            primera_vez TEXT,
            ultima_vez TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_tx_fecha ON transacciones(fecha_date);
        CREATE INDEX IF NOT EXISTS idx_tx_categoria ON transacciones(categoria);
        CREATE INDEX IF NOT EXISTS idx_tx_contraparte ON transacciones(contraparte);
        CREATE INDEX IF NOT EXISTS idx_tx_desc ON transacciones(descripcion_normalizada);
    """)


def normalizar_descripcion(desc):
    """Normaliza una descripcion para agrupar transacciones similares"""
    d = desc.upper().strip()
    # Remover variaciones menores
    d = re.sub(r'[-–—]\s*\d+\s*$', '', d)  # trailing codes like "-12345"
    d = re.sub(r'\s+', ' ', d)
    return d.strip()


def extraer_contraparte(desc):
    """Extrae la contraparte de la descripcion"""
    desc_up = desc.upper().strip()
    # "Para NOMBRE" o "De NOMBRE"
    m = re.search(r"^(?:PARA|DE|ENVIO (?:CON BRE-B|TRANSFIYA) A|RECIBI POR BRE-B DE|DESEMBOLSO|COMPRA EN|PAGO EN QR)\s*(.*)", desc_up)
    if m:
        return m.group(1).strip().rstrip("-–— ")
    # "COMPRA EN TIENDAS ARA" -> "TIENDAS ARA"
    m2 = re.search(r"COMPRA EN\s+(.+?)(?:\s*-.*$|$)", desc_up)
    if m2:
        return m2.group(1).strip()
    return desc_up


def insertar_datos(conn, datos_extractos):
    c = conn.cursor()

    for ex in datos_extractos:
        # Insert extracto
        c.execute("""
            INSERT OR REPLACE INTO extractos
            (archivo, hash, periodo, anio, mes, titular, cuenta,
             saldo_anterior, total_abonos, total_cargos,
             saldo_actual, saldo_promedio, intereses, num_transacciones)
            VALUES (?,?,?,?,?,?,?, ?,?,?, ?,?,?,?)
        """, (
            ex["archivo"], ex["hash"], ex["periodo"], ex["anio"], ex["mes"], ex["titular"], ex["cuenta"],
            float(ex["saldo_anterior"].replace(",","")) if ex["saldo_anterior"] else None,
            float(ex["total_abonos"].replace(",","")) if ex["total_abonos"] else None,
            float(ex["total_cargos"].replace(",","")) if ex["total_cargos"] else None,
            float(ex["saldo_actual"].replace(",","")) if ex["saldo_actual"] else None,
            float(ex["saldo_promedio"].replace(",","")) if ex["saldo_promedio"] else None,
            float(ex["intereses"].replace(",","")) if ex["intereses"] else None,
            len(ex["transacciones"]),
        ))
        extracto_id = c.lastrowid

        for tx in ex["transacciones"]:
            es_ingreso = 1 if tx["valor"] > 0 else 0
            cat = clasificar_transaccion(tx["descripcion"], tx["valor"])
            desc_norm = normalizar_descripcion(tx["descripcion"])
            contraparte = extraer_contraparte(tx["descripcion"])
            try:
                fecha_date = datetime.strptime(tx["fecha"], "%d/%m/%Y").date().isoformat()
            except:
                fecha_date = None

            c.execute("""
                INSERT INTO transacciones
                (extracto_id, fecha, fecha_date, descripcion, descripcion_normalizada,
                 contraparte, valor, es_ingreso, saldo, categoria)
                VALUES (?,?,?,?,?, ?,?,?,?,?)
            """, (
                extracto_id, tx["fecha"], fecha_date, tx["descripcion"], desc_norm,
                contraparte, tx["valor"], es_ingreso, tx["saldo"], cat,
            ))

    conn.commit()


# ============================================================
# DETECCION DE PATRONES
# ============================================================
def detectar_patrones(conn):
    cur = conn.cursor()
    print("\nDetectando patrones recurrentes...")

    # 1. Agrupar por descripcion normalizada + monto exacto (>= 3 ocurrencias)
    cur.execute("""
        SELECT descripcion_normalizada, contraparte, ROUND(valor, 0),
               COUNT(*) as cnt,
               MIN(fecha) as primera, MAX(fecha) as ultima,
               SUM(CASE WHEN es_ingreso=1 THEN 1 ELSE 0 END) as ingresos,
               SUM(CASE WHEN es_ingreso=0 THEN 1 ELSE 0 END) as egresos
        FROM transacciones
        GROUP BY descripcion_normalizada, ROUND(valor, 0)
        HAVING cnt >= 3
        ORDER BY cnt DESC
    """)
    patrones = cur.fetchall()
    print(f"  Patrones mismo monto+descripcion (>=3 ocurrencias): {len(patrones)}")

    patrones_insert = []
    for p in patrones:
        desc_norm, contraparte, monto, cnt, primera, ultima, ingresos, egresos = p
        tipo = "ingreso" if ingresos > egresos else "egreso"
        # Estimar frecuencia
        meses_trans = 1
        try:
            d1 = datetime.strptime(primera, "%Y-%m-%d")
            d2 = datetime.strptime(ultima, "%Y-%m-%d")
            dias = (d2 - d1).days
            meses_trans = max(dias / 30.44, 1)
        except:
            pass
        if meses_trans > 0:
            frecuencia = "mensual" if abs(cnt / meses_trans - 1) < 0.3 else \
                         "quincenal" if abs(cnt / meses_trans - 2) < 0.5 else \
                         "irregular"
            conf = round(cnt / meses_trans, 2)
        else:
            frecuencia = "desconocida"
            conf = 0

        patrones_insert.append((
            tipo, desc_norm, contraparte, float(monto), frecuencia,
            int(cnt), primera, ultima, int(round(meses_trans)), conf
        ))

    cur.executemany("""
        INSERT OR REPLACE INTO patrones_recurrentes
        (tipo, descripcion, contraparte, monto, frecuencia,
         num_ocurrencias, primer_ocurrencia, ultima_ocurrencia,
         meses_activo, confianza)
        VALUES (?,?,?,?,?, ?,?,?,?,?)
    """, patrones_insert)

    # 2. Marcar transacciones como recurrentes
    cur.execute("""
        UPDATE transacciones SET es_recurrente = 1,
            grupo_recurrencia = (
                SELECT descripcion_normalizada
                FROM patrones_recurrentes pr
                WHERE pr.descripcion = transacciones.descripcion_normalizada
                  AND ABS(pr.monto - ROUND(transacciones.valor, 0)) < 1
                LIMIT 1
            )
        WHERE EXISTS (
            SELECT 1 FROM patrones_recurrentes pr
            WHERE pr.descripcion = transacciones.descripcion_normalizada
              AND ABS(pr.monto - ROUND(transacciones.valor, 0)) < 1
              AND pr.num_ocurrencias >= 3
        )
    """)

    # 3. Contrapartes: agrupar y totalizar
    cur.execute("""
        INSERT OR REPLACE INTO contrapartes
        (nombre, tipo, categoria_principal, total_transacciones,
         total_ingresos, total_egresos, primera_vez, ultima_vez)
        SELECT
            contraparte,
            CASE WHEN SUM(es_ingreso) > SUM(1-es_ingreso) THEN 'ingreso' ELSE 'egreso' END,
            (SELECT categoria FROM transacciones t2
             WHERE t2.contraparte = t.contraparte GROUP BY categoria
             ORDER BY COUNT(*) DESC LIMIT 1),
            COUNT(*),
            SUM(CASE WHEN es_ingreso=1 THEN valor ELSE 0 END),
            SUM(CASE WHEN es_ingreso=0 THEN ABS(valor) ELSE 0 END),
            MIN(fecha), MAX(fecha)
        FROM transacciones t
        WHERE contraparte != ''
        GROUP BY contraparte
        HAVING COUNT(*) >= 2
    """)

    conn.commit()
    return patrones_insert


# ============================================================
# REPORTES
# ============================================================
def generar_reportes(conn):
    cur = conn.cursor()
    print("\n" + "=" * 70)
    print("  REPORTE COMPLETO DE FINANZAS NEQUI")
    print("=" * 70)

    # Totales globales
    cur.execute("""
        SELECT COUNT(*),
               SUM(CASE WHEN es_ingreso=1 THEN valor ELSE 0 END),
               SUM(CASE WHEN es_ingreso=0 THEN ABS(valor) ELSE 0 END)
        FROM transacciones
    """)
    total_tx, total_ing, total_egr = cur.fetchone()
    total_ing = total_ing or 0
    total_egr = total_egr or 0
    print(f"\n  Total transacciones: {total_tx}")
    print(f"  Total ingresos:      ${total_ing:,.2f}")
    print(f"  Total egresos:       ${total_egr:,.2f}")
    print(f"  Balance:             ${total_ing - total_egr:,.2f}")

    # Por categoria
    print(f"\n{'='*70}")
    print("  GASTOS POR CATEGORIA")
    print(f"{'='*70}")
    print(f"  {'Categoria':<30s} {'Total':>15s} {'Tx':>8s}")
    print(f"  {'-'*30} {'-'*15} {'-'*8}")
    cur.execute("""
        SELECT categoria, COUNT(*), SUM(ABS(valor))
        FROM transacciones WHERE es_ingreso=0
        GROUP BY categoria ORDER BY SUM(ABS(valor)) DESC
    """)
    for cat, cnt, total in cur.fetchall():
        print(f"  {cat:<30s} ${total:>12,.2f} {cnt:>8d}")

    # Ingresos por categoria
    print(f"\n{'='*70}")
    print("  INGRESOS POR CATEGORIA")
    print(f"{'='*70}")
    print(f"  {'Categoria':<30s} {'Total':>15s} {'Tx':>8s}")
    print(f"  {'-'*30} {'-'*15} {'-'*8}")
    cur.execute("""
        SELECT categoria, COUNT(*), SUM(valor)
        FROM transacciones WHERE es_ingreso=1
        GROUP BY categoria ORDER BY SUM(valor) DESC
    """)
    for cat, cnt, total in cur.fetchall():
        print(f"  {cat:<30s} ${total:>12,.2f} {cnt:>8d}")

    # ============================================================
    # PATRONES DE SUELDO / INGRESO PERIODICO
    # ============================================================
    print(f"\n{'='*70}")
    print("  PATRONES DE INGRESO PERIODICO (POSIBLE SUELDO)")
    print(f"{'='*70}")
    cur.execute("""
        SELECT pr.descripcion, pr.contraparte, pr.monto, pr.frecuencia,
               pr.num_ocurrencias, pr.primer_ocurrencia, pr.ultima_ocurrencia
        FROM patrones_recurrentes pr
        WHERE pr.tipo = 'ingreso' AND pr.num_ocurrencias >= 3
        ORDER BY pr.num_ocurrencias DESC
    """)
    ingresos_periodicos = cur.fetchall()
    if ingresos_periodicos:
        print(f"  {'Contraparte':<35s} {'Monto':>12s} {'Frec':>10s} {'Veces':>6s} {'Desde':>12s}")
        print(f"  {'-'*35} {'-'*12} {'-'*10} {'-'*6} {'-'*12}")
        for p in ingresos_periodicos:
            desc, contra, monto, freq, cnt, primera, ultima = p
            print(f"  {contra[:34]:<35s} ${monto:>10,.0f} {freq:>10s} {cnt:>6d} {primera[:10]:>12s}")
    else:
        print("  (ningun patron de ingreso periodico detectado)")

    # ============================================================
    # PAGOS RECURRENTES A PERSONAS/EMPRESAS
    # ============================================================
    print(f"\n{'='*70}")
    print("  PAGOS RECURRENTES A PERSONAS/EMPRESAS (>=3 ocurrencias)")
    print(f"{'='*70}")
    cur.execute("""
        SELECT pr.descripcion, pr.contraparte, pr.monto, pr.frecuencia,
               pr.num_ocurrencias, pr.primer_ocurrencia, pr.ultima_ocurrencia
        FROM patrones_recurrentes pr
        WHERE pr.tipo = 'egreso' AND pr.num_ocurrencias >= 3
        ORDER BY pr.num_ocurrencias DESC
    """)
    pagos_rec = cur.fetchall()
    if pagos_rec:
        print(f"  {'Descripcion/Contraparte':<40s} {'Monto':>10s} {'Frec':>10s} {'Veces':>6s} {'Periodo':>22s}")
        print(f"  {'-'*40} {'-'*10} {'-'*10} {'-'*6} {'-'*22}")
        for p in pagos_rec:
            desc, contra, monto, freq, cnt, primera, ultima = p
            label = (contra or desc)[:39]
            periodo = f"{primera[:10]} -> {ultima[:10]}" if primera and ultima else ""
            print(f"  {label:<40s} ${monto:>8,.0f} {freq:>10s} {cnt:>6d} {periodo:>22s}")
    else:
        print("  (ningun patron de pago recurrente detectado)")

    # ============================================================
    # TOP CONTRAPARTES
    # ============================================================
    print(f"\n{'='*70}")
    print("  TOP CONTRAPARTES (mas transaccionadas)")
    print(f"{'='*70}")
    print(f"  {'Nombre':<30s} {'Tipo':>8s} {'Tx':>6s} {'Total':>15s}")
    print(f"  {'-'*30} {'-'*8} {'-'*6} {'-'*15}")
    cur.execute("""
        SELECT nombre, tipo, total_transacciones,
               total_ingresos, total_egresos
        FROM contrapartes
        ORDER BY total_transacciones DESC
        LIMIT 30
    """)
    for row in cur.fetchall():
        nombre, tipo, tx_cnt, t_ing, t_egr = row
        total = t_ing - t_egr
        print(f"  {nombre[:29]:<30s} {tipo:>8s} {tx_cnt:>6d} ${total:>12,.2f}")

    # ============================================================
    # DETALLE MENSUAL
    # ============================================================
    print(f"\n{'='*70}")
    print("  EVOLUCION MENSUAL")
    print(f"{'='*70}")
    print(f"  {'Periodo':<10s} {'Ingresos':>14s} {'Gastos':>14s} {'Balance':>14s} {'Tx':>6s}")
    print(f"  {'-'*10} {'-'*14} {'-'*14} {'-'*14} {'-'*6}")
    cur.execute("""
        SELECT e.periodo,
               COALESCE(SUM(CASE WHEN t.es_ingreso=1 THEN t.valor ELSE 0 END), 0),
               COALESCE(SUM(CASE WHEN t.es_ingreso=0 THEN ABS(t.valor) ELSE 0 END), 0),
               COUNT(*)
        FROM extractos e
        LEFT JOIN transacciones t ON t.extracto_id = e.id
        GROUP BY e.id ORDER BY e.anio, e.mes
    """)
    for per, ing, egr, cnt in cur.fetchall():
        bal = ing - egr
        print(f"  {per:<10s} ${ing:>11,.2f} ${egr:>11,.2f} ${bal:>11,.2f} {cnt:>6d}")

    return ingresos_periodicos, pagos_rec


def exportar_json(conn):
    cur = conn.cursor()
    data = {"extractos": [], "transacciones": [], "patrones": [], "contrapartes": []}

    cur.execute("SELECT * FROM extractos ORDER BY anio, mes")
    cols = [d[0] for d in cur.description]
    for row in cur.fetchall():
        data["extractos"].append(dict(zip(cols, row)))

    cur.execute("SELECT * FROM transacciones ORDER BY fecha_date")
    cols = [d[0] for d in cur.description]
    for row in cur.fetchall():
        d = dict(zip(cols, row))
        d["valor"] = float(d["valor"]) if d["valor"] else None
        d["saldo"] = float(d["saldo"]) if d["saldo"] else None
        data["transacciones"].append(d)

    cur.execute("SELECT * FROM patrones_recurrentes ORDER BY num_ocurrencias DESC")
    cols = [d[0] for d in cur.description]
    for row in cur.fetchall():
        data["patrones"].append(dict(zip(cols, row)))

    cur.execute("SELECT * FROM contrapartes ORDER BY total_transacciones DESC")
    cols = [d[0] for d in cur.description]
    for row in cur.fetchall():
        data["contrapartes"].append(dict(zip(cols, row)))

    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nJSON exportado a: {JSON_PATH}")
    return data


# ============================================================
# MAIN
# ============================================================
def main():
    # 1. Unlock PDFs
    unlock_pdfs()

    # 2. Parse all PDFs
    print("\nExtrayendo datos de todos los PDFs...")
    files = sorted([f for f in os.listdir(UNLOCKED_DIR) if f.endswith(".pdf")])
    datos = []
    for i, f in enumerate(files, 1):
        path = os.path.join(UNLOCKED_DIR, f)
        # Calcular hash del PDF
        file_hash = ""
        try:
            with open(path, "rb") as fh:
                file_hash = hashlib.md5(fh.read()).hexdigest()
        except:
            pass
        try:
            d = parse_pdf(path)
            d["hash"] = file_hash
            datos.append(d)
            print(f"  [{i}/{len(files)}] {f:40s} -> {d['periodo']:>8s}  ({len(d['transacciones']):3d} tx)")
        except Exception as e:
            print(f"  [{i}/{len(files)}] {f:40s} -> ERROR: {e}")
    print(f"\nTotal extractos procesados: {len(datos)}")

    # 3. Create DB + insert
    print("\nConstruyendo base de datos SQLite...")
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    crear_db(conn)
    insertar_datos(conn, datos)
    print(f"  Transacciones insertadas: {conn.execute('SELECT COUNT(*) FROM transacciones').fetchone()[0]}")

    # 4. Detect patterns
    patrones = detectar_patrones(conn)

    # Veces que vi cada patron
    cur = conn.cursor()
    cur.execute("SELECT COUNT(DISTINCT grupo_recurrencia) FROM transacciones WHERE es_recurrente=1")
    rec_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM transacciones WHERE es_recurrente=1")
    rec_tx = cur.fetchone()[0]
    print(f"  Transacciones marcadas como recurrentes: {rec_tx} ({rec_count} grupos distintos)")

    # 5. Reports
    generar_reportes(conn)

    # 6. Export JSON
    exportar_json(conn)

    conn.close()
    print(f"\n{'='*70}")
    print(f"  BASE DE DATOS: {DB_PATH}")
    print(f"  Puedes conectarte con: sqlite3 \"{DB_PATH}\"")
    print(f"  O importar el JSON en tu app de finanzas")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
