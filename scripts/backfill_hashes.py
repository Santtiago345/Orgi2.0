import sqlite3, os, hashlib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FINAL_DB = os.path.join(BASE, "data", "final_finanzas.db")

def main():
    conn = sqlite3.connect(FINAL_DB)
    c = conn.cursor()

    try:
        c.execute("ALTER TABLE extractos ADD COLUMN hash TEXT")
        print("Columna hash agregada")
    except sqlite3.OperationalError:
        pass

    c.execute("SELECT id, fuente, archivo FROM extractos WHERE hash IS NULL OR hash = ''")
    rows = c.fetchall()
    print(f"Extractos sin hash: {len(rows)}")
    
    updated = 0
    for eid, fuente, archivo in rows:
        ruta_pdf = os.path.join(BASE, "data", fuente, archivo)
        if not os.path.exists(ruta_pdf):
            continue
        try:
            with open(ruta_pdf, "rb") as f:
                file_hash = hashlib.md5(f.read()).hexdigest()
            c.execute("UPDATE extractos SET hash = ? WHERE id = ?", (file_hash, eid))
            updated += 1
        except:
            pass
    
    conn.commit()
    conn.close()
    print(f"Actualizados: {updated}")

if __name__ == "__main__":
    main()
