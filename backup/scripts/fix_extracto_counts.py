import sqlite3, glob, os, shutil, datetime
BASE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'outputs', 'db')
backup_dir = os.path.join(BASE, 'backups')
if not os.path.exists(backup_dir): os.makedirs(backup_dir, exist_ok=True)

for path in glob.glob(os.path.join(BASE, '*.db')):
    name = os.path.basename(path)
    print('Processing', name)
    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = os.path.join(backup_dir, f"{name}.extractos_fix.{ts}.bak")
    shutil.copy2(path, bak)
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    try:
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cur.fetchall()]
    except Exception as e:
        print('  skipped, error listing tables:', e)
        conn.close()
        continue
    if 'extractos' in tables and 'transacciones' in tables:
        cur.execute("SELECT id, num_transacciones FROM extractos")
        updates = 0
        for r in cur.fetchall():
            eid = r[0]
            expected = r[1] or 0
            actual = cur.execute("SELECT COUNT(*) FROM transacciones WHERE extracto_id=?", (eid,)).fetchone()[0]
            if expected != actual:
                cur.execute("UPDATE extractos SET num_transacciones=? WHERE id=?", (actual, eid))
                updates += 1
                print(f"  {name}: extracto {eid} updated {expected} -> {actual}")
        conn.commit()
        if updates==0:
            print('  No extracto count updates needed')
    conn.close()
print('Done')
