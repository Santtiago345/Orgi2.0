import sqlite3
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE, "data", "final_finanzas.db")

def main():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, descripcion FROM transacciones WHERE notas IS NULL OR notas = ''")
    rows = c.fetchall()
    updated = 0
    for tx_id, descripcion in rows:
        if descripcion and descripcion != "Transaccion MyFinance":
            c.execute("UPDATE transacciones SET notas=? WHERE id=?", (descripcion, tx_id))
            updated += 1
    conn.commit()
    conn.close()
    print(f"Actualizadas {updated} transacciones con notas desde descripcion")

if __name__ == "__main__":
    main()
