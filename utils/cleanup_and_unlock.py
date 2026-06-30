"""
PROCESO SEGURO: DESBLOQUEAR -> RENOMBRAR -> COLOCAR -> VERIFICAR -> LIMPIAR

Requerimiento:
- Solo PDFs desbloqueados en data/{nequi,nu,rappicard}/
- Formato: banco_YYYY-MM_tipo.pdf
- Eliminar bloqueados SOLO al final, tras verificacion

FLUJO:
  1. Leer BD para saber que archivos existen y sus periodos
  2. Para cada archivo en disco, buscar su registro en BD (por nombre)
  3. Desbloquearlo con la contrasena
  4. Guardar version desbloqueada con nombre formateado
  5. VERIFICAR que todos esten en su lugar y sean legibles
  6. SOLO ENTONCES: eliminar originales bloqueados y duplicados
"""

import os, re, shutil, sys
from pypdf import PdfReader, PdfWriter
import sqlite3
from collections import defaultdict

BASE = r'C:\Users\Santt\OneDrive\Documentos\Proyectos\Orgi2.0'
DB_PATH = os.path.join(BASE, 'outputs', 'db', 'finanzas_unificadas.db')
PASSWORD = 'REDACTED_PWD'

print("=" * 70)
print("PROCESO DE DESBLOQUEO, RENOMBRE Y LIMPIEZA")
print("=" * 70)

# ============================================================
# 0. CARGAR BD
# ============================================================
print("\n[0] Cargando base de datos...")
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute('SELECT id, fuente, archivo, periodo FROM extractos ORDER BY id')
db_rows = c.fetchall()
conn.close()
print(f"    {len(db_rows)} extractos cargados")

# Indexar por fuente y por nombre de archivo en disco
# DB archivo = '{fuente}_{nombre_original}.pdf' -> en disco es '{nombre_original}.pdf'
db_by_diskname = {}  # {nombre_en_disco: (id, fuente, archivo, periodo)}
for r in db_rows:
    disk_name = re.sub(r'^(nequi|nu|rappicard)_', '', r[2])
    db_by_diskname[disk_name] = r


def parse_periodo(periodo):
    """Extraer (anio, mes) del periodo."""
    if not periodo:
        return None, None
    m = re.match(r'(\d{4})/(\d{2})', periodo)
    if m:
        return int(m.group(1)), int(m.group(2))
    meses = {m: i+1 for i, m in enumerate(
        ['ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic'])}
    m = re.match(r'(\d{1,2})\s+([a-z]{3,})\s+(\d{4})', periodo.lower())
    if m and m.group(2)[:3] in meses:
        return int(m.group(3)), meses[m.group(2)[:3]]
    m = re.search(r'([a-z]{3,})\s+(\d{4})', periodo.lower())
    if m and m.group(1)[:3] in meses:
        return int(m.group(2)), meses[m.group(1)[:3]]
    return None, None


def unlock_pdf(src_path, dst_path, password):
    """Desbloquear o copiar si ya esta desbloqueado."""
    try:
        reader = PdfReader(src_path)
        if reader.is_encrypted:
            if not reader.decrypt(password):
                return False, "Contrasena incorrecta"
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)
        os.makedirs(os.path.dirname(dst_path), exist_ok=True)
        with open(dst_path, 'wb') as f:
            writer.write(f)
        return True, "OK"
    except Exception as e:
        return False, str(e)


# ============================================================
# 1. IDENTIFICAR PDFs EN DISCO
# ============================================================
print("\n[1] Identificando PDFs en data/...")

all_originals = []  # (ruta_completa, fuente, id_db, periodo, anio, mes)

for fuente in ['nequi', 'nu', 'rappicard']:
    dir_path = os.path.join(BASE, 'data', fuente)
    if not os.path.isdir(dir_path):
        continue
    for fname in sorted(os.listdir(dir_path)):
        if not fname.lower().endswith('.pdf'):
            continue
        fp = os.path.join(dir_path, fname)
        
        if fname in db_by_diskname:
            db_rec = db_by_diskname[fname]
            id_db, _, _, periodo = db_rec
            anio, mes = parse_periodo(periodo)
            all_originals.append((fp, fuente, id_db, periodo, anio, mes))
            estado = f"ID={id_db}"
        else:
            # Archivo no registrado en BD (ej. renombres previos)
            anio, mes = None, None
            all_originals.append((fp, fuente, None, None, None, None))
            estado = "SIN REGISTRO"
        
        print(f"    [{fuente:10s}] {estado:12s} {fname}")

originals_with_id = [r for r in all_originals if r[2] is not None]
unknowns = [r for r in all_originals if r[2] is None]
print(f"\n    Total con registro en BD: {len(originals_with_id)}")
print(f"    Sin registro (renombres previos o extra): {len(unknowns)}")

# ============================================================
# 2. DESBLOQUEAR Y RENOMBRAR
# ============================================================
print(f"\n[2] Desbloqueando {len(originals_with_id)} PDFs con clave '{PASSWORD}'...")

# Temp dir para resultados intermedios
TEMP = os.path.join(BASE, 'data', '__temp_unlocked__')
os.makedirs(TEMP, exist_ok=True)

tipo_por_fuente = {'nequi': 'extracto_cuenta', 'nu': 'tarjeta_credito', 'rappicard': 'tarjeta_credito'}

unlocked = []  # (fuente, id_db, dest_name, ruta_temp)
errores = []

for fp, fuente, id_db, periodo, anio, mes in originals_with_id:
    fname = os.path.basename(fp)
    
    if anio and mes:
        dest_name = f'{fuente}_{anio:04d}-{mes:02d}_{tipo_por_fuente[fuente]}.pdf'
    else:
        # Fallback: usar el nombre original
        dest_name = fname
        print(f"    WARN: No se pudo extraer fecha para {fname} (periodo='{periodo}')")
    
    temp_path = os.path.join(TEMP, dest_name)
    ok, msg = unlock_pdf(fp, temp_path, PASSWORD)
    
    if ok:
        unlocked.append((fuente, id_db, dest_name, temp_path))
        print(f"    OK  ID={id_db:<3d} {fname:55s} -> {dest_name}")
    else:
        errores.append((fname, msg))
        print(f"    FAIL ID={id_db:<3d} {fname:55s} - {msg}")

if errores:
    print(f"\n    ERROR: {len(errores)} archivos no se pudieron desbloquear!")
    for fname, msg in errores:
        print(f"      - {fname}: {msg}")
    print("    Abortando. Contrasena incorrecta?")
    shutil.rmtree(TEMP, ignore_errors=True)
    sys.exit(1)

print(f"\n    {len(unlocked)} PDFs desbloqueados exitosamente.")

# ============================================================
# 3. VERIFICAR COBERTURA vs BD
# ============================================================
print("\n[3] Verificando cobertura vs base de datos...")

unlocked_by_fuente = defaultdict(set)
for fuente, id_db, dest_name, _ in unlocked:
    unlocked_by_fuente[fuente].add(id_db)

cobertura_ok = True
for fuente in ['nequi', 'nu', 'rappicard']:
    expected = set(r[0] for r in db_rows if r[1] == fuente)
    actual = unlocked_by_fuente.get(fuente, set())
    missing = expected - actual
    if missing:
        cobertura_ok = False
        print(f"    ERROR [{fuente}]: Faltan {len(missing)} extractos:")
        for mid in sorted(missing):
            rec = [r for r in db_rows if r[0] == mid][0]
            print(f"      ID={mid}: {rec[2]}")
    else:
        print(f"    OK [{fuente}]: {len(actual)}/{len(expected)} cubiertos")

if not cobertura_ok:
    print("\n    ERROR: Cobertura incompleta. Abortando limpieza.")
    print("    Los PDFs desbloqueados quedan en __temp_unlocked__/")
    sys.exit(1)

print("\n    COBERTURA COMPLETA.")

# ============================================================
# 4. COPIAR a data/{fuente}/
# ============================================================
print("\n[4] Copiando PDFs desbloqueados a data/...")

for fuente, id_db, dest_name, temp_path in unlocked:
    dst = os.path.join(BASE, 'data', fuente, dest_name)
    shutil.copy2(temp_path, dst)

print(f"    {len(unlocked)} archivos copiados.")

# ============================================================
# 5. VERIFICACION FINAL
# ============================================================
print("\n[5] VERIFICACION: todos los PDFs desbloqueados estan legibles?")

verificacion_ok = True
for fuente, id_db, dest_name, _ in unlocked:
    dst = os.path.join(BASE, 'data', fuente, dest_name)
    try:
        r = PdfReader(dst)
        if r.is_encrypted:
            print(f"    ERROR: {dest_name} sigue bloqueado!")
            verificacion_ok = False
        elif len(r.pages) == 0:
            print(f"    WARN: {dest_name} tiene 0 paginas")
        else:
            pass  # OK
    except Exception as e:
        print(f"    ERROR: {dest_name} - {e}")
        verificacion_ok = False

if not verificacion_ok:
    print("\n    ERROR: Verificacion fallida. NO se eliminara nada.")
    print("    Los desbloqueados quedan en data/ y __temp_unlocked__/")
    sys.exit(1)

# Segunda verificacion: contar archivos
print("\n[5b] Verificando cantidad de archivos en data/...")
for fuente in ['nequi', 'nu', 'rappicard']:
    dir_path = os.path.join(BASE, 'data', fuente)
    unlocked_in_dir = [r[2] for r in unlocked if r[0] == fuente]
    expected_n = len(unlocked_in_dir)
    actual_n = len([f for f in os.listdir(dir_path) if f.lower().endswith('.pdf') and f in unlocked_in_dir])
    print(f"    [{fuente}] esperados={expected_n} presentes={actual_n}")
    if actual_n < expected_n:
        verificacion_ok = False

if not verificacion_ok:
    print("\n    ERROR: No todos los PDFs esperados estan en data/. Abortando limpieza.")
    sys.exit(1)

print("\n    VERIFICACION EXITOSA.")

# ============================================================
# 6. LIMPIEZA (SOLO AHORA)
# ============================================================
print("\n[6] LIMPIEZA: eliminando PDFs bloqueados y duplicados...")

deleted = 0
kept_unlocked = set(r[2] for r in unlocked)

for fuente in ['nequi', 'nu', 'rappicard']:
    dir_path = os.path.join(BASE, 'data', fuente)
    if not os.path.isdir(dir_path):
        continue
    for fname in list(os.listdir(dir_path)):
        if not fname.lower().endswith('.pdf'):
            continue
        if fname in kept_unlocked:
            continue  # Mantener!
        fp = os.path.join(dir_path, fname)
        os.remove(fp)
        deleted += 1
        print(f"    DELETE [{fuente}] {fname}")

shutil.rmtree(TEMP, ignore_errors=True)
print(f"\n    Eliminados: {deleted} archivos bloqueados/duplicados")

# ============================================================
# RESUMEN
# ============================================================
print("\n" + "=" * 70)
print("PROCESO COMPLETADO EXITOSAMENTE")
print("=" * 70)
for fuente in ['nequi', 'nu', 'rappicard']:
    files = sorted([r[2] for r in unlocked if r[0] == fuente])
    print(f"\n  [{fuente}] ({len(files)} archivos):")
    for f in files:
        print(f"    {f}")
print()
print("  Solo PDFs desbloqueados con nombres formateados en data/")
print("=" * 70)
