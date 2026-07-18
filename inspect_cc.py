import sqlite3, os

BASE = os.path.dirname(os.path.abspath(__file__))
for db_path, name in [
    (os.path.join(BASE, "data", "nu", "nu_finanzas.db"), "Nu"),
    (os.path.join(BASE, "data", "rappicard", "rappicard_finanzas.db"), "Rappicard")
]:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    # Find transactions with installments
    cursor.execute("SELECT fecha, descripcion, valor, cuota_actual, total_cuotas FROM transacciones WHERE total_cuotas > 1 LIMIT 5")
    rows = cursor.fetchall()
    print(f"--- {name} Installment transactions ---")
    for r in rows:
        print(r)
        
    # Find Tuboleta around Feb 14
    cursor.execute("SELECT fecha, descripcion, valor, cuota_actual, total_cuotas FROM transacciones WHERE LOWER(descripcion) LIKE '%tuboleta%' OR LOWER(descripcion) LIKE '%boleta%'")
    tuboleta = cursor.fetchall()
    print(f"--- {name} Tuboleta transactions ---")
    for r in tuboleta:
        print(r)
    conn.close()

# Also check MyFinance for tuboleta
conn = sqlite3.connect(os.path.join(BASE, "data", "myfinance", "MyFinance.db"))
cursor = conn.cursor()
cursor.execute("SELECT date, comment, amountInDefaultCurrency FROM 'transaction' WHERE LOWER(comment) LIKE '%tuboleta%' OR LOWER(comment) LIKE '%boleta%'")
myf_tuboleta = cursor.fetchall()
print(f"--- MyFinance Tuboleta transactions ---")
for r in myf_tuboleta:
    print(r)
conn.close()

