import sqlite3
import os

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DB_PATH = os.path.join(BASE, 'data', 'myfinance', 'MyFinance.db')

RELEVANT_TABLES = [
    'transaction',
    'category',
    'sync_link',
    'account',
    'account_balance',
]
IGNORED_TABLES = [
    'android_metadata',
    'app_notifications_data',
    'app_notifications_settings',
    'budget',
    'colors',
    'debt_account',
    'goal',
    'rates',
    'regular_payment_period',
    'reminding',
    'sync_action',
    'sync_data',
    'sync_file',
    'syncable_settings',
    'tag',
    'transfer',
    'user',
    'user_profile',
    'in_remote_settings',
]

if not os.path.exists(DB_PATH):
    raise FileNotFoundError(f"MyFinance.db no encontrado en {DB_PATH}")

print('DB PATH:', DB_PATH)
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

print('\nTABLAS RELEVANTES:')
for t in RELEVANT_TABLES:
    print('  -', t)

print('\nTABLAS IGNORADAS:')
for t in IGNORED_TABLES:
    print('  -', t)

print('\nTABLAS EN LA BD:')
for row in cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall():
    print('  ', row['name'])

for t in RELEVANT_TABLES:
    print(f"\n=== TABLA: {t} ===")
    try:
        cols = cur.execute(f"PRAGMA table_info('{t}')").fetchall()
        print('COLUMNS:', [c[1] for c in cols])
        count = cur.execute(f"SELECT COUNT(*) FROM '{t}'").fetchone()[0]
        print('COUNT:', count)
        if t in ('transaction', 'category', 'account', 'expense', 'income', 'transfer'):
            for r in cur.execute(f"SELECT * FROM '{t}' LIMIT 5").fetchall():
                print('   ', dict(r))
    except Exception as e:
        print('  ERR', e)

print('\nDISTRIBUCIÓN DE TIPOS EN transaction:')
for row in cur.execute("SELECT type, COUNT(*) as cnt FROM 'transaction' GROUP BY type ORDER BY cnt DESC"):
    print('  ', dict(row))

print('\nMUESTRA DE CATEGORÍAS:')
for row in cur.execute("SELECT uid, title, type FROM category ORDER BY title LIMIT 20"):
    print('  ', dict(row))

print('\nSYNC_LINK MAPPINGS:')
for row in cur.execute("SELECT entityType, otherType, COUNT(*) as cnt FROM sync_link GROUP BY entityType, otherType"):
    print('  ', dict(row))

conn.close()
