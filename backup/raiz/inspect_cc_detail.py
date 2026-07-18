import sqlite3, os

BASE = os.path.dirname(os.path.abspath(__file__))
conn = sqlite3.connect(os.path.join(BASE, "data", "rappicard", "rappicard_finanzas.db"))
cursor = conn.cursor()
cursor.execute("SELECT fecha, descripcion, valor, cuota_actual, total_cuotas, extracto_id FROM transacciones WHERE LOWER(descripcion) LIKE '%tuboleta%' ORDER BY fecha")
rows = cursor.fetchall()
print("All TuBoleta in Rappicard:")
for r in rows:
    print(r)
conn.close()

