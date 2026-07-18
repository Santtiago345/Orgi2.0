import sqlite3, glob, os, shutil, datetime
BASE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'outputs', 'db')
backup_dir = os.path.join(BASE, 'backups')
if not os.path.exists(backup_dir): os.makedirs(backup_dir, exist_ok=True)

for path in glob.glob(os.path.join(BASE, '*.db')):
    name = os.path.basename(path)
    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = os.path.join(backup_dir, f"{name}.{ts}.bak")
    print('Backing up', name, '->', bak)
    shutil.copy2(path, bak)

    conn = sqlite3.connect(path)
    cur = conn.cursor()
    try:
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cur.fetchall()]
    except Exception as e:
        print('  Skipping', name, 'error listing tables:', e)
        conn.close()
        continue

    total_updates = 0
    if 'transacciones' in tables:
        cols = [r[1] for r in cur.execute("PRAGMA table_info(transacciones)").fetchall()]
        colset = set(cols)
        if 'es_ingreso' in colset and 'valor' in colset:
            # ingresos negativos -> make positive
            cur.execute("UPDATE transacciones SET valor = ABS(valor) WHERE es_ingreso=1 AND valor<0")
            u1 = cur.rowcount
            # gastos positivos -> make negative
            cur.execute("UPDATE transacciones SET valor = -ABS(valor) WHERE es_ingreso=0 AND valor>0")
            u2 = cur.rowcount
            total_updates += (u1 + u2)
            if u1+u2>0:
                print(f"  {name}: fixed {u1} ingresos and {u2} gastos (valor/es_ingreso)")
        if 'tipo' in colset and 'monto' in colset:
            # income negative -> positive
            cur.execute("UPDATE transacciones SET monto = ABS(monto) WHERE (LOWER(tipo) LIKE '%income%' OR LOWER(tipo) LIKE '%ingreso%') AND monto<0")
            u3 = cur.rowcount
            # expense positive -> negative
            cur.execute("UPDATE transacciones SET monto = -ABS(monto) WHERE (LOWER(tipo) LIKE '%expense%' OR LOWER(tipo) LIKE '%gasto%') AND monto>0")
            u4 = cur.rowcount
            total_updates += (u3 + u4)
            if u3+u4>0:
                print(f"  {name}: fixed {u3} income and {u4} expense rows (monto/tipo)")
    conn.commit()
    conn.close()
    if total_updates==0:
        print('  No sign fixes needed for', name)
    else:
        print('  Total updates for', name, total_updates)
print('Done')
