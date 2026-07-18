import sqlite3
import os

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_DIR, "data", "final_finanzas.db")

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

def test_tuboleta():
    print("--- Test TuBoleta ---")
    cursor.execute("SELECT id, fecha, descripcion, valor_total, total_cuotas FROM compras_diferidas WHERE LOWER(descripcion) LIKE '%tuboleta%' AND fecha = '2026-02-14'")
    rows = cursor.fetchall()
    
    if not rows:
        print("FAIL: No se encontró compra diferida de TuBoleta el 14 de Febrero.")
        return
        
    for r in rows:
        print(f"Compra Encontrada: {r}")
        compra_id = r[0]
        
        cursor.execute("SELECT num_cuota, valor_cuota, estado_pago FROM cuotas_tarjeta WHERE compra_diferida_id = ?", (compra_id,))
        cuotas = cursor.fetchall()
        print(f"Cuotas para compra {compra_id}:")
        for c in cuotas:
            print(f"  {c}")
            
        valor_total = r[3]
        total_cuotas = r[4]
        
        # Evaluar que las cuotas de ESTA compra en específico no sumen en transacciones
        cursor.execute("SELECT COUNT(*) FROM transacciones WHERE fecha = '2026-02-14' AND LOWER(descripcion) LIKE '%tuboleta%' AND original_id IS NULL AND fuente IN ('Rappicard', 'Nu')")
        tx_count = cursor.fetchone()[0]
        if tx_count > 0:
            print(f"FAIL: Existen transacciones en el balance general de TuBoleta duplicadas. No deberían estar ahí.")
        else:
            print("OK: No hay duplicados en la tabla de transacciones de balance general.")

test_tuboleta()
conn.close()
