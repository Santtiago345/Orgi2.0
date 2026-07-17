import sqlite3, glob, os, json, datetime
BASE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'outputs', 'db')
reports_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'outputs', 'reports')
if not os.path.exists(reports_dir): os.makedirs(reports_dir, exist_ok=True)

report = {"generated_at": datetime.datetime.now().isoformat(), "databases": {}}

for path in glob.glob(os.path.join(BASE, '*.db')):
    name = os.path.basename(path)
    info = {"issues": []}
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    try:
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cur.fetchall()]
    except Exception as e:
        info['error'] = str(e)
        report['databases'][name] = info
        continue

    if 'transacciones' in tables:
        cols = [r[1] for r in cur.execute("PRAGMA table_info(transacciones)").fetchall()]
        colset = set(cols)
        # Check es_ingreso/valor convention
        if 'es_ingreso' in colset and 'valor' in colset:
            # ingresos negativos
            n1 = cur.execute("SELECT COUNT(*) FROM transacciones WHERE es_ingreso=1 AND valor<0").fetchone()[0]
            if n1>0:
                info['issues'].append({"type":"ingreso_sign_incorrecto","count":n1})
            # gastos positivos
            n2 = cur.execute("SELECT COUNT(*) FROM transacciones WHERE es_ingreso=0 AND valor>0").fetchone()[0]
            if n2>0:
                info['issues'].append({"type":"gasto_sign_incorrecto","count":n2})
        # Check tipo/monto convention
        if 'tipo' in colset and 'monto' in colset:
            # income with negative monto
            n3 = cur.execute("SELECT COUNT(*) FROM transacciones WHERE (LOWER(tipo) LIKE '%income%' OR LOWER(tipo) LIKE '%ingreso%') AND monto<0").fetchone()[0]
            if n3>0:
                info['issues'].append({"type":"tipo_income_sign_incorrecto","count":n3})
            n4 = cur.execute("SELECT COUNT(*) FROM transacciones WHERE (LOWER(tipo) LIKE '%expense%' OR LOWER(tipo) LIKE '%gasto%') AND monto>0").fetchone()[0]
            if n4>0:
                info['issues'].append({"type":"tipo_expense_sign_incorrecto","count":n4})
        # Check missing fecha_date or fecha
        if 'fecha_date' in colset:
            n5 = cur.execute("SELECT COUNT(*) FROM transacciones WHERE fecha_date IS NULL OR fecha_date='' ").fetchone()[0]
            if n5>0:
                info['issues'].append({"type":"missing_fecha_date","count":n5})
        if 'fecha' in colset:
            n6 = cur.execute("SELECT COUNT(*) FROM transacciones WHERE fecha IS NULL OR fecha='' ").fetchone()[0]
            if n6>0:
                info['issues'].append({"type":"missing_fecha","count":n6})

    # Generic checks: extractos num_transacciones mismatch
    if 'extractos' in tables and 'transacciones' in tables:
        # Try to compare counts by extracto id
        try:
            cur.execute("SELECT id, num_transacciones FROM extractos")
            for r in cur.fetchall():
                eid = r['id']
                expected = r['num_transacciones'] or 0
                actual = cur.execute("SELECT COUNT(*) FROM transacciones WHERE extracto_id=?", (eid,)).fetchone()[0]
                if expected != actual:
                    info['issues'].append({"type":"extracto_count_mismatch","extracto_id":eid, "expected": expected, "actual": actual})
        except Exception:
            pass

    report['databases'][name] = info
    conn.close()

out_path = os.path.join(reports_dir, f"integrity_report_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(report, f, indent=2, ensure_ascii=False)

print('Integrity report written to', out_path)
print(json.dumps(report, indent=2, ensure_ascii=False))
