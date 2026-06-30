"""
Analisis completo de extractos Nequi
======================================
- Desbloquea todos los PDFs
- Extrae datos de cada extracto (periodo, saldos, transacciones)
- Identifica meses faltantes
- Genera reporte completo en JSON + consola
"""
import os
import re
import json
import shutil
import pdfplumber
from pypdf import PdfReader, PdfWriter
from datetime import datetime

PDF_DIR = r"C:\Users\Santt\OneDrive\Documentos\Proyectos\Orgi2.0\PDFs_Gmail NEQUI"
UNLOCKED_DIR = os.path.join(PDF_DIR, "unlocked")
PASSWORD = "REDACTED_PWD"
OUTPUT_JSON = os.path.join(PDF_DIR, "analisis_nequi.json")
OUTPUT_TXT = os.path.join(PDF_DIR, "reporte_nequi.txt")

MESES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
]


def unlock_pdfs():
    print("Desbloqueando PDFs...")
    if os.path.exists(UNLOCKED_DIR):
        shutil.rmtree(UNLOCKED_DIR)
    os.makedirs(UNLOCKED_DIR)

    pdfs = [f for f in os.listdir(PDF_DIR) if f.endswith(".pdf") and f != "unlocked"]
    ok = 0
    fail = 0
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
            print(f"  ERROR desbloqueando {f}: {e}")
            fail += 1
    print(f"  Desbloqueados: {ok}  |  Fallos: {fail}")
    return ok, fail


def parse_nequi_pdf(filepath):
    """Extrae toda la informacion de un extracto Nequi"""
    result = {
        "archivo": os.path.basename(filepath),
        "periodo": None,
        "anio": None,
        "mes": None,
        "titular": None,
        "email": None,
        "cuenta": None,
        "saldo_anterior": None,
        "total_abonos": None,
        "total_cargos": None,
        "saldo_actual": None,
        "saldo_promedio": None,
        "intereses": None,
        "retefuente": None,
        "num_transacciones": 0,
        "transacciones": [],
    }

    with pdfplumber.open(filepath) as pdf:
        full_text = ""
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                full_text += t + "\n"

    # --- Periodo ---
    period_match = re.search(
        r"per[ií]odo\s+de:\s*(\d{4})/(\d{2})/(\d{2})\s+a\s+(\d{4})/(\d{2})/(\d{2})",
        full_text
    )
    if period_match:
        anio = int(period_match.group(1))
        mes = int(period_match.group(2))
        result["periodo"] = f"{anio}/{mes:02d}"
        result["anio"] = anio
        result["mes"] = mes
    else:
        # Fallback: extraer del nombre del archivo
        name_match = re.search(r"(\d{4})(\d{2})", os.path.basename(filepath))
        if name_match:
            result["anio"] = int(name_match.group(1))
            result["mes"] = int(name_match.group(2))
            result["periodo"] = f"{result['anio']}/{result['mes']:02d}"

    # --- Titular ---
    name_match = re.search(r"Extracto.*\n\s*(.+?)(?:\n|$)", full_text)
    if name_match:
        result["titular"] = name_match.group(1).strip()

    # --- Email ---
    email_match = re.search(r"([\w.]+@[\w.]+)", full_text)
    if email_match:
        result["email"] = email_match.group(1)

    # --- Cuenta ---
    account_match = re.search(r"N[uú]mero\s+de\s+dep[óo]sito[^:]*:\s*(\d+)", full_text)
    if account_match:
        result["cuenta"] = account_match.group(1)

    # --- Resumen financiero ---
    def extract_val(text, key):
        # Busca patrones como: "Saldo anterior $151,107.03"
        pat = re.compile(rf"{re.escape(key)}\s*\$?([\d.,]+)")
        m = pat.search(text)
        if m:
            return m.group(1)
        # Busca en tabla: "Saldo anterior", None, "$151,107.03", ...
        pat2 = re.compile(rf"{re.escape(key)}[,\s]+[\w\s]*\$?([\d.,]+)")
        m2 = pat2.search(text)
        if m2:
            return m2.group(1)
        return None

    result["saldo_anterior"] = extract_val(full_text, "Saldo anterior")
    result["total_abonos"] = extract_val(full_text, "Total abonos")
    result["total_cargos"] = extract_val(full_text, "Total cargos")
    result["saldo_actual"] = extract_val(full_text, "Saldo actual")
    result["saldo_promedio"] = extract_val(full_text, "Saldo promedio")
    result["intereses"] = extract_val(full_text, "intereses pagados")
    result["retefuente"] = extract_val(full_text, "Retefuente")

    # --- Transacciones ---
    lines = full_text.split("\n")
    in_transactions = False
    for line in lines:
        if "Fecha del movimiento" in line:
            in_transactions = True
            continue
        if not in_transactions:
            continue
        if "Los dep" in line or "Puedes consultar" in line:
            break
        line = line.strip()
        if not line:
            continue
        # Formato: "31/05/2026  COMPRA EN BOGOTA 70  $-21,800.00  $1,242,628.44"
        tx_match = re.match(
            r"(\d{2}/\d{2}/\d{4})\s+(.+?)\s+\$?(-?\d[\d.,]*)\s+\$?(-?\d[\d.,]*)",
            line
        )
        if tx_match:
            tx = {
                "fecha": tx_match.group(1),
                "descripcion": tx_match.group(2).strip(),
                "valor": tx_match.group(3),
                "saldo": tx_match.group(4),
            }
            result["transacciones"].append(tx)

    result["num_transacciones"] = len(result["transacciones"])
    return result


def analyze_all():
    print("\nAnalizando todos los extractos...")
    results = []
    files = sorted([f for f in os.listdir(UNLOCKED_DIR) if f.endswith(".pdf")])
    total = len(files)

    for i, f in enumerate(files, 1):
        path = os.path.join(UNLOCKED_DIR, f)
        try:
            data = parse_nequi_pdf(path)
            results.append(data)
            print(f"  [{i}/{total}] {f} -> {data['periodo']} | "
                  f"{data['num_transacciones']} tx | "
                  f"Saldo: ${data['saldo_actual'] or '?'}")
        except Exception as e:
            print(f"  [{i}/{total}] {f} -> ERROR: {e}")

    return results


def build_coverage(data):
    """Construye matriz de cobertura por anio/mes"""
    coverage = {}
    for d in data:
        a = d["anio"]
        m = d["mes"]
        if a is None or m is None:
            continue
        if a not in coverage:
            coverage[a] = {}
        coverage[a][m] = d

    # Determinar rango
    anios = sorted(coverage.keys())
    if not anios:
        return coverage, [], []

    missing = []
    extra = []

    for anio in range(min(anios), max(anios) + 1):
        hoy = datetime.now()
        for mes in range(1, 13):
            # No contar meses futuros
            if anio > hoy.year or (anio == hoy.year and mes > hoy.month):
                continue
            if anio not in coverage or mes not in coverage[anio]:
                missing.append((anio, mes))
            else:
                extra.append((anio, mes, coverage[anio][mes]))

    return coverage, missing, extra


def print_report(data, missing, present):
    lines = []
    lines.append("=" * 80)
    lines.append("  REPORTE COMPLETO - EXTRACTOS NEQUI")
    lines.append("  Titular: JOEL SANTIAGO NEUTA JASPE")
    lines.append("=" * 80)

    # Coverage table
    lines.append("\n" + "-" * 80)
    lines.append("  MATRIZ DE COBERTURA POR MES")
    lines.append("-" * 80)

    header = "  " + "     ".join(MESES[:6])
    header2 = "  " + "     ".join(MESES[6:])
    lines.append(header)
    lines.append(header2)

    coverage = {}
    for a, m, d in present:
        if a not in coverage:
            coverage[a] = {}
        coverage[a][m] = d

    for anio in sorted(coverage.keys()):
        row1 = f"  {anio}  "
        row2 = f"  {anio}  "
        for mes in range(1, 7):
            if mes in coverage.get(anio, {}):
                row1 += f"  OK  "
            else:
                row1 += f"  --  "
        for mes in range(7, 13):
            if mes in coverage.get(anio, {}):
                row2 += f"  OK  "
            else:
                row2 += f"  --  "
        lines.append(row1)
        lines.append(row2)
        lines.append("")

    # Missing months
    lines.append("-" * 80)
    lines.append("  MESES FALTANTES")
    lines.append("-" * 80)
    if missing:
        for anio, mes in missing:
            lines.append(f"    * {MESES[mes-1]} {anio}")
    else:
        lines.append("  (ninguno - todos los meses disponibles)")

    # Summary stats
    lines.append("\n" + "-" * 80)
    lines.append("  RESUMEN FINANCIERO GLOBAL")
    lines.append("-" * 80)

    total_abonos = 0
    total_cargos = 0
    total_intereses = 0
    count = 0
    for d in data:
        if d["total_abonos"]:
            val = float(d["total_abonos"].replace(",", ""))
            total_abonos += val
            count += 1
        if d["total_cargos"]:
            val = float(d["total_cargos"].replace(",", ""))
            total_cargos += val
        if d["intereses"]:
            val = float(d["intereses"].replace(",", ""))
            total_intereses += val

    lines.append(f"  Total de extractos analizados: {len(data)}")
    lines.append(f"  Suma total abonos (ingresos): ${total_abonos:,.2f}")
    lines.append(f"  Suma total cargos (gastos):   ${total_cargos:,.2f}")
    lines.append(f"  Suma total intereses:          ${total_intereses:,.2f}")

    # Detail per month
    lines.append("\n" + "-" * 80)
    lines.append("  DETALLE MENSUAL")
    lines.append("-" * 80)

    for d in sorted(data, key=lambda x: (x["anio"] or 0, x["mes"] or 0)):
        lines.append(f"\n  {MESES[(d['mes'] or 1) - 1] if d['mes'] else '?'} {d['anio'] or '?'} "
                     f"({d['archivo']})")
        lines.append(f"    Saldo anterior: ${d['saldo_anterior'] or '?'}")
        lines.append(f"    Total abonos:   ${d['total_abonos'] or '?'}")
        lines.append(f"    Total cargos:   ${d['total_cargos'] or '?'}")
        lines.append(f"    Saldo actual:   ${d['saldo_actual'] or '?'}")
        lines.append(f"    Saldo promedio: ${d['saldo_promedio'] or '?'}")
        lines.append(f"    Intereses:      ${d['intereses'] or '?'}")
        lines.append(f"    Transacciones:  {d['num_transacciones']}")
        # Top 5 transactions by value
        txs = sorted(d["transacciones"],
                     key=lambda t: abs(float(t["valor"].replace(",", "").replace("$", ""))),
                     reverse=True)[:5]
        for tx in txs:
            lines.append(f"      [{tx['fecha']}] {tx['descripcion'][:45]:45s} {tx['valor']:>15s}")

    return "\n".join(lines)


def main():
    # Step 1: Unlock
    ok, _ = unlock_pdfs()
    if ok == 0:
        print("No se pudo desbloquear ningun PDF. Abortando.")
        return

    # Step 2: Analyze
    data = analyze_all()

    # Step 3: Build coverage
    _, missing, present = build_coverage(data)

    # Step 4: Generate report
    report = print_report(data, missing, present)

    # Step 5: Save
    with open(OUTPUT_TXT, "w", encoding="utf-8") as f:
        f.write(report)
    # Save structured data
    json_output = []
    for d in data:
        j = {k: v for k, v in d.items() if k != "transacciones"}
        j["num_transacciones"] = d["num_transacciones"]
        j["transacciones"] = d["transacciones"][:100]  # limit for size
        json_output.append(j)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(json_output, f, indent=2, ensure_ascii=False)

    print(f"\nReporte guardado en: {OUTPUT_TXT}")
    print(f"Datos JSON guardados en: {OUTPUT_JSON}")

    # Print to console
    print(report)


if __name__ == "__main__":
    main()
