import sqlite3
import os
import re
from datetime import datetime, timedelta

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE, "data", "final_finanzas.db")

MESES = {
    'ENE':1,'FEB':2,'MAR':3,'ABR':4,'MAY':5,'JUN':6,
    'JUL':7,'AGO':8,'SEP':9,'OCT':10,'NOV':11,'DIC':12,
    'ENERO':1,'FEBRERO':2,'MARZO':3,'ABRIL':4,'MAYO':5,'JUNIO':6,
    'JULIO':7,'AGOSTO':8,'SEPTIEMBRE':9,'OCTUBRE':10,'NOVIEMBRE':11,'DICIEMBRE':12,
    'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,
    'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12,
}


def fmt_val(v):
    if v is None:
        return "NULL"
    return f"{v:.2f}"


def parse_fecha(s):
    if not s:
        return None
    s = s.strip()
    m = re.search(r'(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})', s)
    if m:
        dia = int(m.group(1))
        mes = MESES.get(m.group(2).upper()[:3])
        anio = int(m.group(3))
        if mes:
            try:
                return datetime(anio, mes, dia)
            except ValueError:
                return None
    return None


def extraer_fechas_desde_periodo(periodo):
    if not periodo:
        return None, None
    # Formato Nu: "09 MAY a 20 MAY 2026"
    m = re.match(r'(\d{1,2})\s+(\w+)\s+a\s+(\d{1,2})\s+(\w+)\s+(\d{4})', periodo)
    if m:
        dia_fin = int(m.group(3))
        mes_fin = MESES.get(m.group(4).upper()[:3])
        anio = int(m.group(5))
        if mes_fin:
            fecha_corte = datetime(anio, mes_fin, dia_fin) + timedelta(days=1)
            try:
                fecha_corte_dt = datetime(anio, mes_fin, dia_fin) + timedelta(days=1)
            except ValueError:
                fecha_corte_dt = None
            fecha_pago_mes = mes_fin + 1 if mes_fin < 12 else 1
            fecha_pago_anio = anio if mes_fin < 12 else anio + 1
            try:
                fecha_pago_dt = datetime(fecha_pago_anio, fecha_pago_mes, 10)
            except ValueError:
                fecha_pago_dt = None
            fecha_corte_str = fecha_corte_dt.strftime('%d %b %Y').upper() if fecha_corte_dt else None
            fecha_pago_str = fecha_pago_dt.strftime('%d %b %Y').upper() if fecha_pago_dt else None
            return fecha_corte_str, fecha_pago_str
    # Formato RappiCard: "30 sep 2025 a 30 oct 2025"
    m = re.match(r'(\d{1,2})\s+(\w+)\s+(\d{4})\s+a\s+(\d{1,2})\s+(\w+)\s+(\d{4})', periodo)
    if m:
        dia_fin = int(m.group(4))
        mes_fin = MESES.get(m.group(5).upper()[:3])
        anio_fin = int(m.group(6))
        if mes_fin:
            fecha_pago = datetime(anio_fin, mes_fin, min(dia_fin, 28)) + timedelta(days=10)
            fecha_pago_str = fecha_pago.strftime('%d %b %Y').upper() if fecha_pago else None
            return None, fecha_pago_str
    return None, None


def main():
    print("=" * 60)
    print("Migracion: Corregir extractos de tarjetas de credito")
    print("=" * 60)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("SELECT * FROM extractos WHERE fuente IN ('nu','rappicard') ORDER BY id")
    rows = c.fetchall()
    print(f"\nRegistros de TC encontrados: {len(rows)}\n")

    fixed = 0

    for r in rows:
        eid = r["id"]
        fuente = r["fuente"]
        antes = dict(r)
        cambios = {}

        if fuente == "nu":
            if r["total_pagar"] is not None and r["pago_minimo"] is not None:
                if r["total_pagar"] >= r["pago_minimo"] * 1.5:
                    print(f"  [Nu id={eid}] total_pagar={fmt_val(r['total_pagar'])} parece cupo -> {fmt_val(r['pago_minimo'])}")
                    cambios["total_pagar"] = r["pago_minimo"]

            if r["cupo_total"] is None or r["cupo_total"] != 1000000.0:
                if r["cupo_total"] != 1000000.0:
                    print(f"  [Nu id={eid}] cupo_total={fmt_val(r['cupo_total'])} -> 1000000.00")
                    cambios["cupo_total"] = 1000000.0

        if fuente == "rappicard":
            if r["total_pagar"] is None or r["total_pagar"] < 1000:
                if r["pago_minimo"] is not None:
                    cambios["total_pagar"] = r["pago_minimo"]
                    print(f"  [RappiCard id={eid}] total_pagar={fmt_val(r['total_pagar'])} -> {fmt_val(r['pago_minimo'])}")

        if r["saldo_anterior"] is None:
            cambios["saldo_anterior"] = 0.0
            print(f"  [{fuente} id={eid}] saldo_anterior=NULL -> 0.00")

        if r["fecha_corte"] is None or r["fecha_pago"] is None:
            fc, fp = extraer_fechas_desde_periodo(r["periodo"])
            if fc and r["fecha_corte"] is None:
                cambios["fecha_corte"] = fc
                print(f"  [{fuente} id={eid}] fecha_corte=NULL -> {fc}")
            if fp and r["fecha_pago"] is None:
                cambios["fecha_pago"] = fp
                print(f"  [{fuente} id={eid}] fecha_pago=NULL -> {fp}")

        if not cambios:
            continue

        set_clause = ", ".join(f"{k}=?" for k in cambios)
        c.execute(f"UPDATE extractos SET {set_clause} WHERE id=?", (*cambios.values(), eid))

        c.execute("SELECT * FROM extractos WHERE id=?", (eid,))
        despues = dict(c.fetchone())

        print(f"    ANTES:   tot={fmt_val(antes['total_pagar'])}, min={fmt_val(antes['pago_minimo'])}, cupo={fmt_val(antes['cupo_total'])}, saldo_ant={fmt_val(antes['saldo_anterior'])}, corte={antes['fecha_corte']}, pago={antes['fecha_pago']}")
        print(f"    DESPUES: tot={fmt_val(despues['total_pagar'])}, min={fmt_val(despues['pago_minimo'])}, cupo={fmt_val(despues['cupo_total'])}, saldo_ant={fmt_val(despues['saldo_anterior'])}, corte={despues['fecha_corte']}, pago={despues['fecha_pago']}")
        print()

        fixed += 1

    conn.commit()
    conn.close()

    print(f"Total de correcciones: {fixed}")
    print("Migracion completada.")


if __name__ == "__main__":
    main()
