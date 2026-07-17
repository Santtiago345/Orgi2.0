import sqlite3, glob, os
BASE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'outputs', 'db')
if not os.path.exists(BASE):
    print('No outputs/db directory')
else:
    for f in glob.glob(os.path.join(BASE, '*.db')):
        print('DB:', os.path.basename(f))
        conn = sqlite3.connect(f)
        cur = conn.cursor()
        tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        for t in tables:
            print('  -', t)
            try:
                cnt = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                print('     rows:', cnt)
            except Exception as e:
                print('     (no count)', e)
        conn.close()