import sqlite3
import os
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FINAL_DB = os.path.join(BASE, "data", "final_finanzas.db")

DAVIPLATA_DB = os.path.join(BASE, "data", "daviplata", "daviplata_finanzas.db")
DALE_DB = os.path.join(BASE, "data", "dale", "dale_finanzas.db")

BANKS = [
    ("daviplata", DAVIPLATA_DB, 4000),
    ("dale", DALE_DB, 3000),
]

MESES = {'ENE':1,'FEB':2,'MAR':3,'ABR':4,'MAY':5,'JUN':6,'JUL':7,'AGO':8,'SEP':9,'OCT':10,'NOV':11,'DIC':12,
         'ENERO':1,'FEBRERO':2,'MARZO':3,'ABRIL':4,'MAYO':5,'JUNIO':6,'JULIO':7,'AGOSTO':8,'SEPTIEMBRE':9,'OCTUBRE':10,'NOVIEMBRE':11,'DICIEMBRE':12}

def merge():
    conn_final = sqlite3.connect(FINAL_DB)
    c = conn_final.cursor()

    for fuente, db_path, id_offset in BANKS:
        if not os.path.exists(db_path):
            print(f"  [{fuente}] DB no encontrada: {db_path}")
            continue

        src = sqlite3.connect(db_path)
        src.row_factory = sqlite3.Row
        sc = src.cursor()

        sc.execute("SELECT * FROM extractos")
        extractos = [dict(r) for r in sc.fetchall()]
        sc.execute("SELECT * FROM transacciones")
        transacciones = [dict(r) for r in sc.fetchall()]
        src.close()

        print(f"\n  [{fuente}] {len(extractos)} extractos, {len(transacciones)} transacciones")

        for ext in extractos:
            new_id = ext['id'] + id_offset

            c.execute("SELECT COUNT(*) FROM extractos WHERE id=?", (new_id,))
            if c.fetchone()[0] > 0:
                c.execute("DELETE FROM extractos WHERE id=?", (new_id,))
                c.execute("DELETE FROM transacciones WHERE extracto_id=?", (new_id,))
                print(f"    [REEMPLAZADO] id={new_id}")

            c.execute("""INSERT INTO extractos (id, archivo, fuente, tipo, periodo, anio, mes, titular, num_transacciones, saldo_actual)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (new_id, ext.get('archivo',''), fuente, 'cuenta',
                 ext.get('periodo'), ext.get('anio'), ext.get('mes'),
                 ext.get('titular'), ext.get('num_transacciones', 0),
                 ext.get('saldo_actual')))

            print(f"    [+] Extracto {new_id}: {ext.get('periodo','?')} | {len([t for t in transacciones if t.get('extracto_id') == ext['id']])} tx")

        for tx in transacciones:
            ext_id_new = tx.get('extracto_id', 0) + id_offset
            fecha_str = tx.get('fecha_date') or tx.get('fecha')
            try:
                fecha_date = datetime.strptime(fecha_str[:10], "%Y-%m-%d").date()
            except (ValueError, TypeError):
                continue

            valor = tx.get('valor', 0)
            desc = tx.get('descripcion_normalizada') or tx.get('descripcion', '')
            cat = tx.get('categoria', 'Sin clasificar')
            es_ingreso = 1 if valor > 0 else 0

            c.execute("""INSERT INTO transacciones (fecha, fecha_date, descripcion, valor, entidad, cruzada, categoria, es_ingreso, notas, extracto_id, metodo_pago)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (fecha_date.isoformat(), fecha_date, desc,
                 valor, fuente, 0, cat, es_ingreso,
                 '', ext_id_new, 'transferencia'))

        conn_final.commit()
        print(f"    Total insertado: {len(extractos)} extractos, {len(transacciones)} transacciones")

    conn_final.close()
    print("\n  Merge completado.")

if __name__ == "__main__":
    merge()
