import sqlite3, os
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
path = os.path.join(BASE, 'outputs', 'db', 'finanzas_unificadas.db')
print('DB:', path)
conn = sqlite3.connect(path)
c = conn.cursor()
# Get existing columns
c.execute("PRAGMA table_info(transacciones)")
cols = [r[1] for r in c.fetchall()]
print('Existing cols:', cols)
added = False
if 'notas' not in cols:
    print('Adding column notas')
    c.execute("ALTER TABLE transacciones ADD COLUMN notas TEXT")
    added = True
if 'metodo_pago' not in cols:
    print('Adding column metodo_pago')
    c.execute("ALTER TABLE transacciones ADD COLUMN metodo_pago TEXT")
    added = True
if added:
    conn.commit()
    print('Columns added')
else:
    print('No changes needed')
conn.close()
