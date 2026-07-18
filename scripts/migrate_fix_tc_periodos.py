import sqlite3, os, re

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE, "data", "final_finanzas.db")

MESES = {
    'ene': 1, 'feb': 2, 'mar': 3, 'abr': 4, 'may': 5, 'jun': 6,
    'jul': 7, 'ago': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dic': 12,
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
    'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4, 'mayo': 5, 'junio': 6,
    'julio': 7, 'agosto': 8, 'septiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12,
    'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
    'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12,
}

def extraer_anio_mes(periodo):
    if not periodo:
        return None, None
    periodo = periodo.strip()

    m = re.match(r'^(\d{4})/(\d{2})$', periodo)
    if m:
        return int(m.group(1)), int(m.group(2))

    m = re.match(r'^(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})\s+a\s+(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})$', periodo)
    if m:
        mes2 = MESES.get(m.group(5).lower()[:3])
        anio2 = int(m.group(6))
        if mes2:
            return anio2, mes2

    m = re.match(r'^(\d{1,2})\s+([A-Za-z]+)\s+a\s+(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})$', periodo)
    if m:
        mes2 = MESES.get(m.group(4).lower()[:3])
        anio2 = int(m.group(5))
        if mes2:
            return anio2, mes2

    return None, None


def main():
    print("=" * 60)
    print("Migración: Corregir anio/mes en extractos de TC")
    print("=" * 60)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("SELECT id, fuente, periodo, anio, mes FROM extractos WHERE fuente IN ('nu','rappicard') AND (anio IS NULL OR mes IS NULL)")
    rows = c.fetchall()
    print(f"\nRegistros con NULL: {len(rows)}")

    actualizados = 0
    for r in rows:
        eid, fuente, periodo, anio_actual, mes_actual = r
        anio_nuevo, mes_nuevo = extraer_anio_mes(periodo)

        if anio_nuevo is None and mes_nuevo is None:
            print(f"  [SKIP] id={eid} ({fuente}): no se pudo parsear periodo='{periodo}'")
            continue

        anio_final = anio_nuevo if anio_nuevo is not None else anio_actual
        mes_final = mes_nuevo if mes_nuevo is not None else mes_actual

        if anio_final == anio_actual and mes_final == mes_actual:
            print(f"  [SKIP] id={eid} ({fuente}): ya tiene anio={anio_actual}, mes={mes_actual}")
            continue

        c.execute("UPDATE extractos SET anio=?, mes=? WHERE id=?", (anio_final, mes_final, eid))
        actualizados += 1
        print(f"  [OK] id={eid} ({fuente}): periodo='{periodo}' -> anio={anio_final}, mes={mes_final}")

    conn.commit()
    conn.close()

    print(f"\nTotal actualizados: {actualizados}")
    print("Migración completada.")


if __name__ == "__main__":
    main()
