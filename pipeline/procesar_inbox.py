"""
PROCESAR INBOX — Pipeline automatizado de ingesta de PDFs
===========================================================
FLUJO:
  1. Escanea data/inbox/ en busca de PDFs nuevos
  2. Por cada PDF:
     a. Desbloquea con contraseña REDACTED_PWD
     b. Identifica banco (Nequi, Nu, RappiCard) extrayendo texto
     c. Extrae período (año, mes) del contenido
     d. Renombra con formato: {banco}_{YYYY-MM}_{tipo}.pdf
     e. Mueve a data/{banco}/
  3. Ejecuta el pipeline completo de sistematización:
     a. analisis_unificado.py   → finanzas_unificadas.db
     b. construir_bd_unificada.py → finanzas_unificada_completa.db
     c. analisis_tarjetas_completo.py → reportes por entidad

USO:
  python pipeline/procesar_inbox.py
  python pipeline/procesar_inbox.py --pipeline-only   (solo reprocesar, sin inbox)
  python pipeline/procesar_inbox.py --inbox-only      (solo procesar inbox, sin pipeline)
"""

import os, re, sys, shutil, subprocess
import pdfplumber
from pypdf import PdfReader, PdfWriter

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INBOX_DIR = os.path.join(BASE, "data", "inbox")
PASSWORD = "REDACTED_PWD"

FUENTES = {
    "nequi": {
        "dir": os.path.join(BASE, "data", "nequi"),
        "tipo": "cuenta",
        "keywords": ["extracto de deposito", "extracto de dep", "nequi"],
        "identificadores": ["Nequi", "EXT_NEQUI"],
    },
    "nu": {
        "dir": os.path.join(BASE, "data", "nu"),
        "tipo": "tarjeta_credito",
        "keywords": ["nu financiera", "ayuda@nu.com.co", "nu colombia"],
        "identificadores": ["Nu Financiera"],
    },
    "rappicard": {
        "dir": os.path.join(BASE, "data", "rappicard"),
        "tipo": "tarjeta_credito",
        "keywords": ["rappicard", "davivienda", "credit_card_statement"],
        "identificadores": ["RappiCard", "Davivienda"],
    },
}

MESES = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

MESES_LARGO = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}

# ============================================================
# 1. EXTRACCIÓN DE TEXTO
# ============================================================
def extraer_texto(pdf_path):
    """Extrae texto plano de todas las páginas del PDF."""
    texto = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for p in pdf.pages:
                t = p.extract_text()
                if t:
                    texto += t + "\n"
    except Exception as e:
        print(f"  ERROR extrayendo texto: {e}")
    return texto


# ============================================================
# 2. IDENTIFICACIÓN DE BANCO
# ============================================================
def identificar_banco(texto):
    """Detecta qué banco generó el extracto."""
    t = texto.lower()
    for banco, info in FUENTES.items():
        for kw in info["keywords"]:
            if kw in t:
                return banco
        for ident in info["identificadores"]:
            if ident.lower() in t:
                return banco
    return None


# ============================================================
# 3. EXTRACCIÓN DE PERÍODO
# ============================================================
def extraer_periodo_nequi(texto):
    """Extrae año/mes de un extracto Nequi."""
    # Formato: "período de: YYYY/MM" o "periodo de: YYYY/MM"
    m = re.search(r"per[ií]odo\s+de:\s*(\d{4})/(\d{2})", texto, re.IGNORECASE)
    if m:
        return int(m.group(1)), int(m.group(2))
    # Formato: "Febrero 2020" en algún encabezado
    m = re.search(r"(Enero|Febrero|Marzo|Abril|Mayo|Junio|Julio|Agosto|Septiembre|Octubre|Noviembre|Diciembre)\s+(\d{4})", texto, re.IGNORECASE)
    if m:
        mes = MESES_LARGO.get(m.group(1).lower())
        if mes:
            return int(m.group(2)), mes
    return None, None


def _extraer_periodo_nu_desde(texto):
    """Busca patrón de período Nu en un texto y retorna (anio, mes_final)."""
    pat = r"(\d{1,2})\s+([A-Za-z]+)\s*[-–—]+\s*(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})"
    m = re.search(pat, texto)
    if m:
        mes1 = MESES.get(m.group(2).lower()[:3])
        mes2 = MESES.get(m.group(4).lower()[:3])
        anio = int(m.group(5))
        if mes1 and mes2:
            return anio, mes2 if mes1 != mes2 else mes1
        elif mes1:
            return anio, mes1
    return None, None

def extraer_periodo_nu(texto):
    """Extrae año/mes de un extracto Nu.
    Nu nombra sus extractos por el MES DE CORTE (mes final del período).
    Ej: '21 MAY - 19 JUN 2026' → mes=6 (Junio)"""
    anio, mes = _extraer_periodo_nu_desde(texto)
    if anio:
        return anio, mes
    # Fallback: línea siguiente a "periodo facturado"
    lines = texto.split("\n")
    for i, line in enumerate(lines):
        if "periodo facturado" in line.lower() and i + 1 < len(lines):
            anio, mes = _extraer_periodo_nu_desde(lines[i + 1])
            if anio:
                return anio, mes
    return None, None


def extraer_periodo_rappicard(texto):
    """Extrae año/mes de un extracto RappiCard.
    El período está en formato:
      Periodo facturado
      Desde 31 oct 2025
      Hasta 27 nov 2025
    Se usa el mes de la fecha "Desde" (primer mes del período)."""
    m = re.search(r"Desde\s+(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", texto)
    if m:
        mes = MESES.get(m.group(2).lower()[:3])
        anio = int(m.group(3))
        if mes:
            return anio, mes
    return None, None


EXTRACTORES = {
    "nequi": extraer_periodo_nequi,
    "nu": extraer_periodo_nu,
    "rappicard": extraer_periodo_rappicard,
}


# ============================================================
# 4. GENERAR NOMBRE DE ARCHIVO
# ============================================================
def generar_nombre(banco, anio, mes, conflicto=False):
    """Genera el nombre de archivo estándar."""
    tipo = FUENTES[banco]["tipo"]
    nombre = f"{banco}_{anio:04d}-{mes:02d}_{tipo}.pdf"
    if conflicto:
        base = nombre.replace(".pdf", "")
        nombre = f"{base}_v{conflicto}.pdf"
    return nombre


# ============================================================
# 5. DESBLOQUEAR PDF
# ============================================================
def desbloquear_pdf(origen, destino):
    """Desbloquea un PDF protegido con contraseña."""
    try:
        reader = PdfReader(origen)
        if reader.is_encrypted:
            reader.decrypt(PASSWORD)
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)
        with open(destino, "wb") as f:
            writer.write(f)
        return True
    except Exception as e:
        print(f"  ERROR desbloqueando: {e}")
        return False


# ============================================================
# 6. PROCESAR UN PDF DEL INBOX
# ============================================================
def procesar_pdf(ruta_pdf):
    """Procesa un único PDF: desbloquea, identifica, renombra y mueve."""
    nombre_orig = os.path.basename(ruta_pdf)
    print(f"\n  Procesando: {nombre_orig}")

    # 6a. Desbloquear a temporal
    temp_dir = os.path.join(BASE, "data", "__temp_inbox__")
    os.makedirs(temp_dir, exist_ok=True)
    temp_pdf = os.path.join(temp_dir, "temp_unlocked.pdf")

    if not desbloquear_pdf(ruta_pdf, temp_pdf):
        print(f"  [SKIP] No se pudo desbloquear {nombre_orig}")
        return False

    # 6b. Extraer texto
    texto = extraer_texto(temp_pdf)
    if not texto:
        print(f"  [SKIP] No se pudo extraer texto de {nombre_orig}")
        limpiar_temp(temp_dir)
        return False

    # 6c. Identificar banco
    banco = identificar_banco(texto)
    if not banco:
        print(f"  [SKIP] No se pudo identificar el banco en {nombre_orig}")
        print(f"    Primeros 200 chars: {texto[:200]}")
        limpiar_temp(temp_dir)
        return False
    print(f"    Banco: {banco}")

    # 6d. Extraer período
    extractor = EXTRACTORES[banco]
    anio, mes = extractor(texto)
    if not anio or not mes:
        print(f"  [SKIP] No se pudo extraer el período de {nombre_orig}")
        limpiar_temp(temp_dir)
        return False
    print(f"    Periodo: {anio:04d}-{mes:02d}")

    # 6e. Generar nombre y mover
    dir_destino = FUENTES[banco]["dir"]
    os.makedirs(dir_destino, exist_ok=True)
    nombre_final = generar_nombre(banco, anio, mes)

    # Manejar conflictos: si ya existe, agregar sufijo _v2, _v3...
    contador = 0
    while os.path.exists(os.path.join(dir_destino, nombre_final)):
        contador += 1
        nombre_final = generar_nombre(banco, anio, mes, conflicto=contador + 1)

    destino = os.path.join(dir_destino, nombre_final)
    shutil.move(temp_pdf, destino)
    print(f"    -> {destino}")

    # 6f. Limpiar temp
    limpiar_temp(temp_dir)

    # 6g. Verificar
    if os.path.exists(destino):
        print(f"    [OK] Archivo colocado correctamente")
        return True
    else:
        print(f"    [ERROR] No se pudo mover el archivo")
        return False


def limpiar_temp(temp_dir):
    """Limpia archivos temporales."""
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir, ignore_errors=True)


# ============================================================
# 7. PROCESAR TODO EL INBOX
# ============================================================
def procesar_inbox():
    """Procesa todos los PDFs en la carpeta inbox."""
    if not os.path.exists(INBOX_DIR):
        print(f"  La carpeta {INBOX_DIR} no existe. Creando...")
        os.makedirs(INBOX_DIR)
        print("  Carpeta creada. Coloca aquí los PDFs nuevos.")
        return 0

    pdfs = [f for f in os.listdir(INBOX_DIR) if f.lower().endswith(".pdf")]
    if not pdfs:
        print(f"  No hay PDFs en {INBOX_DIR}")
        print(f"  Coloca los extractos nuevos en esa carpeta y vuelve a ejecutar.")
        return 0

    print(f"\n{'='*70}")
    print(f"  PROCESANDO {len(pdfs)} PDF(s) DEL INBOX")
    print(f"{'='*70}")

    exitosos = 0
    fallidos = 0

    for fname in sorted(pdfs):
        ruta = os.path.join(INBOX_DIR, fname)
        if procesar_pdf(ruta):
            exitosos += 1
        else:
            fallidos += 1

    print(f"\n  RESULTADO INBOX: {exitosos} exitosos, {fallidos} fallidos")

    # Mover los procesados a una subcarpeta "procesados/"
    if exitosos > 0:
        proc_dir = os.path.join(INBOX_DIR, "procesados")
        os.makedirs(proc_dir, exist_ok=True)
        for fname in sorted(pdfs):
            ruta = os.path.join(INBOX_DIR, fname)
            if os.path.exists(ruta):
                try:
                    shutil.move(ruta, os.path.join(proc_dir, fname))
                except:
                    pass
        print(f"  PDFs originales movidos a {proc_dir}/")

    return exitosos


# ============================================================
# 8. EJECUTAR PIPELINE
# ============================================================
def ejecutar_pipeline():
    """Ejecuta los scripts del pipeline en orden."""
    print(f"\n{'='*70}")
    print(f"  EJECUTANDO PIPELINE DE SISTEMATIZACION")
    print(f"{'='*70}")

    scripts = [
        ("analisis_unificado.py", "Construyendo base de datos unificada..."),
        ("construir_bd_unificada.py", "Construyendo base de datos completa con cruces..."),
        ("analisis_tarjetas_completo.py", "Analizando tarjetas de credito..."),
    ]

    for script, desc in scripts:
        ruta = os.path.join(BASE, "analysis", script)
        if not os.path.exists(ruta):
            print(f"  [SKIP] {script} no encontrado")
            continue
        print(f"\n  --- {desc} ---")
        print(f"  Ejecutando: python analysis/{script}")
        try:
            resultado = subprocess.run(
                [sys.executable, ruta],
                capture_output=True, text=True, timeout=300
            )
            if resultado.returncode == 0:
                print(f"  [OK] {script} completado")
                # Mostrar últimas líneas relevantes
                lineas = resultado.stdout.strip().split("\n")
                for l in lineas[-5:]:
                    if l.strip():
                        print(f"    {l.strip()}")
            else:
                print(f"  [ERROR] {script} falló (código {resultado.returncode})")
                for l in resultado.stderr.strip().split("\n")[-5:]:
                    if l.strip():
                        print(f"    ERROR: {l.strip()}")
        except subprocess.TimeoutExpired:
            print(f"  [TIMEOUT] {script} excedió el tiempo límite")
        except Exception as e:
            print(f"  [ERROR] {script}: {e}")

    print(f"\n{'='*70}")
    print(f"  PIPELINE COMPLETADO")
    print(f"{'='*70}")


# ============================================================
# MAIN
# ============================================================
def main():
    print("=" * 70)
    print("  AUTO-PROCESADOR DE EXTRACTOS BANCARIOS")
    print(f"  Inbox: {INBOX_DIR}")
    print("=" * 70)

    solo_pipeline = "--pipeline-only" in sys.argv
    solo_inbox = "--inbox-only" in sys.argv

    procesados = 0

    if not solo_pipeline:
        procesados = procesar_inbox()
        if procesados == 0 and not solo_inbox:
            print("\n  No hay PDFs nuevos que procesar.")
            continuar = input("  Ejecutar pipeline de todas formas? (s/N): ").strip().lower()
            if continuar != "s":
                print("  Saliendo.")
                return

    if not solo_inbox:
        ejecutar_pipeline()

    print(f"\n  Listo. Sistema actualizado.")


if __name__ == "__main__":
    main()
