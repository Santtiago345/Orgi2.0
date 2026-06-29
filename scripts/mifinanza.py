"""
MiFinanza - Aplicacion de Gestion Financiera Personal
======================================================
"""
import sqlite3
import json
from datetime import datetime, date
import sys
from tabulate import tabulate

BASE = r"C:\Users\Santt\OneDrive\Documentos\Proyectos\Orgi2.0"
DB_PATH = os.path.join(BASE, "data", "myfinance", "MyFinance.db")
DATA_DIR = os.path.join(BASE, "data")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    # New tables for our app
    c.executescript("""
        CREATE TABLE IF NOT EXISTS budget (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            month TEXT NOT NULL,
            year INTEGER NOT NULL,
            category TEXT NOT NULL,
            limit_amount REAL NOT NULL,
            spent REAL DEFAULT 0,
            created TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS debt_account (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            total_debt REAL NOT NULL,
            interest_rate REAL DEFAULT 0,
            min_payment REAL DEFAULT 0,
            due_day INTEGER,
            is_active INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS goal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            target_amount REAL NOT NULL,
            saved_amount REAL DEFAULT 0,
            deadline TEXT,
            priority INTEGER DEFAULT 1,
            is_completed INTEGER DEFAULT 0,
            created TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS income (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            amount REAL NOT NULL,
            date TEXT NOT NULL,
            is_recurring INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS expense (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            amount REAL NOT NULL,
            description TEXT,
            date TEXT NOT NULL,
            payment_method TEXT
        );
    """)
    conn.commit()
    conn.close()

# ---------- COMMANDS ----------
def cmd_add_income(args):
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO income (source, amount, date, is_recurring) VALUES (?,?,?,?)",
              (args[0], float(args[1]), args[2] if len(args)>2 else date.today().isoformat(), 1 if "--recurring" in args else 0))
    conn.commit()
    conn.close()
    print(f"Ingreso registrado: {args[0]} - ${float(args[1]):,.0f}")

def cmd_add_expense(args):
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO expense (category, amount, description, date, payment_method) VALUES (?,?,?,?,?)",
              (args[0], float(args[1]), args[2] if len(args)>2 else "",
               args[3] if len(args)>3 else date.today().isoformat(),
               args[4] if len(args)>4 else ""))
    conn.commit()
    conn.close()
    print(f"Gasto registrado: {args[0]} - ${float(args[1]):,.0f}")

def cmd_balance(args):
    conn = get_db()
    c = conn.cursor()
    # Income this month
    m = date.today().month
    y = date.today().year
    c.execute("SELECT COALESCE(SUM(amount),0) FROM income WHERE strftime('%m', date) = ? AND strftime('%Y', date) = ?",
              (f"{m:02d}", str(y)))
    total_income = c.fetchone()[0]
    c.execute("SELECT COALESCE(SUM(amount),0) FROM expense WHERE strftime('%m', date) = ? AND strftime('%Y', date) = ?",
              (f"{m:02d}", str(y)))
    total_expense = c.fetchone()[0]
    # Debts
    c.execute("SELECT COALESCE(SUM(total_debt),0) FROM debt_account WHERE is_active=1")
    total_debt = c.fetchone()[0]
    c.execute("SELECT COALESCE(SUM(min_payment),0) FROM debt_account WHERE is_active=1")
    total_min = c.fetchone()[0]
    conn.close()
    print(f"\n--- Balance Mensual ({date.today().strftime('%B %Y')}) ---")
    print(f"  Ingresos del mes:     ${total_income:>10,.0f}")
    print(f"  Gastos del mes:       ${total_expense:>10,.0f}")
    print(f"  Disponible:           ${total_income - total_expense:>10,.0f}")
    print(f"\n  Deuda total:          ${total_debt:>10,.0f}")
    print(f"  Pagos minimos mes:    ${total_min:>10,.0f}")
    print(f"  Libre despues deudas: ${total_income - total_expense - total_min:>10,.0f}")

def cmd_debts(args):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM debt_account WHERE is_active=1")
    rows = c.fetchall()
    conn.close()
    if not rows:
        print("No hay deudas registradas. Usa: python mifinanza.py add-debt")
        return
    print("\n--- DEUDAS ACTIVAS ---")
    data = []
    for r in rows:
        data.append([r["name"], f"${r['total_debt']:,.0f}",
                     f"{r['interest_rate']:.1f}%", f"${r['min_payment']:,.0f}",
                     f"Dia {r['due_day']}" if r['due_day'] else "-"])
    print(tabulate(data, headers=["Nombre", "Deuda", "Interes", "Minimo", "Vence"], tablefmt="grid"))
    total = sum(r["total_debt"] for r in rows)
    mins = sum(r["min_payment"] for r in rows)
    print(f"\n  TOTAL: ${total:,.0f}  |  Minimos: ${mins:,.0f}/mes")

def cmd_goals(args):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM goal WHERE is_completed=0 ORDER BY priority")
    rows = c.fetchall()
    conn.close()
    if not rows:
        print("No hay metas activas. Usa: python mifinanza.py add-goal")
        return
    print("\n--- METAS DE AHORRO ---")
    data = []
    for r in rows:
        pct = (r["saved_amount"] / r["target_amount"]) * 100 if r["target_amount"] > 0 else 0
        data.append([r["name"], f"${r['target_amount']:,.0f}",
                     f"${r['saved_amount']:,.0f}", f"{pct:.0f}%",
                     r["deadline"] or "-",
                     "ALTA" if r["priority"]==1 else "MEDIA" if r["priority"]==2 else "BAJA"])
    print(tabulate(data, headers=["Meta", "Meta", "Ahorrado", "Avance", "Fecha limite", "Prioridad"], tablefmt="grid"))

def cmd_budget(args):
    conn = get_db()
    c = conn.cursor()
    m = date.today().month
    y = date.today().year
    if args and args[0] == "set" and len(args) >= 3:
        c.execute("INSERT OR REPLACE INTO budget (month, year, category, limit_amount, spent) VALUES (?,?,?,?,COALESCE((SELECT spent FROM budget WHERE month=? AND year=? AND category=?),0))",
                  (f"{m:02d}", y, args[1], float(args[2]), f"{m:02d}", y, args[1]))
        conn.commit()
        print(f"Presupuesto para '{args[1]}': ${float(args[2]):,.0f}")
    else:
        c.execute("SELECT * FROM budget WHERE month=? AND year=? ORDER BY category", (f"{m:02d}", y))
        rows = c.fetchall()
        if not rows:
            print(f"No hay presupuesto para {date.today().strftime('%B %Y')}")
            print("Usa: python mifinanza.py budget set <categoria> <monto>")
        else:
            print(f"\n--- PRESUPUESTO {date.today().strftime('%B %Y').upper()} ---")
            data = []
            for r in rows:
                pct = (r["spent"] / r["limit_amount"]) * 100 if r["limit_amount"] > 0 else 0
                bar = "=" * int(pct/10) + " " * (10 - int(pct/10))
                data.append([r["category"], f"${r['limit_amount']:,.0f}",
                            f"${r['spent']:,.0f}", f"{pct:.0f}%", bar])
            print(tabulate(data, headers=["Categoria", "Limite", "Gastado", "%", "Uso"], tablefmt="grid"))
            total_lim = sum(r["limit_amount"] for r in rows)
            total_spent = sum(r["spent"] for r in rows)
            print(f"\n  TOTAL: ${total_spent:,.0f} de ${total_lim:,.0f}")
    conn.close()

def cmd_report(args):
    conn = get_db()
    c = conn.cursor()
    m = date.today().month
    y = date.today().year
    # Expenses by category
    c.execute("""
        SELECT category, SUM(amount) as total, COUNT(*) as count
        FROM expense
        WHERE strftime('%m', date) = ? AND strftime('%Y', date) = ?
        GROUP BY category ORDER BY total DESC
    """, (f"{m:02d}", str(y)))
    expenses = c.fetchall()
    # Income
    c.execute("SELECT SUM(amount) FROM income WHERE strftime('%m', date) = ? AND strftime('%Y', date) = ?",
              (f"{m:02d}", str(y)))
    total_income = c.fetchone()[0] or 0
    c.execute("SELECT SUM(amount) FROM expense WHERE strftime('%m', date) = ? AND strftime('%Y', date) = ?",
              (f"{m:02d}", str(y)))
    total_expense = c.fetchone()[0] or 0
    # Debts
    c.execute("SELECT SUM(min_payment) FROM debt_account WHERE is_active=1")
    mins = c.fetchone()[0] or 0
    conn.close()

    print(f"\n=== REPORTE MENSUAL: {date.today().strftime('%B %Y')} ===")
    print(f"Ingresos:      ${total_income:>10,.0f}")
    print(f"Gastos:        ${total_expense:>10,.0f}")
    print(f"Deudas (min):  ${mins:>10,.0f}")
    print(f"Balance:       ${total_income - total_expense - mins:>10,.0f}")
    print(f"\nGastos por categoria:")
    for e in expenses:
        pct = (e["total"] / total_expense) * 100 if total_expense > 0 else 0
        print(f"  {e['category']:25s} ${e['total']:>8,.0f}  ({pct:5.1f}%)  {e['count']} transacciones")

def cmd_add_debt(args):
    if len(args) < 4:
        print("Uso: python mifinanza.py add-debt <nombre> <deuda_total> <pago_minimo> <dia_vencimiento> [interes]")
        return
    conn = get_db()
    c = conn.cursor()
    interest = float(args[4]) if len(args) > 4 else 0
    c.execute("INSERT INTO debt_account (name, total_debt, min_payment, due_day, interest_rate) VALUES (?,?,?,?,?)",
              (args[0], float(args[1]), float(args[2]), int(args[3]), interest))
    conn.commit()
    conn.close()
    print(f"Deuda registrada: {args[0]} - ${float(args[1]):,.0f}")

def cmd_add_goal(args):
    if len(args) < 2:
        print("Uso: python mifinanza.py add-goal <nombre> <monto> [fecha_limite] [prioridad]")
        return
    conn = get_db()
    c = conn.cursor()
    deadline = args[2] if len(args) > 2 else None
    priority = int(args[3]) if len(args) > 3 else 1
    c.execute("INSERT INTO goal (name, target_amount, deadline, priority) VALUES (?,?,?,?)",
              (args[0], float(args[1]), deadline, priority))
    conn.commit()
    conn.close()
    print(f"Meta creada: {args[0]} - ${float(args[1]):,.0f}")

def cmd_pay_debt(args):
    if len(args) < 2:
        print("Uso: python mifinanza.py pay-debt <nombre_deuda> <monto>")
        return
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE debt_account SET total_debt = total_debt - ? WHERE name = ? AND is_active=1",
              (float(args[1]), args[0]))
    if c.rowcount == 0:
        print(f"No se encontro deuda: {args[0]}")
    else:
        # Also update min payment proportionally
        c.execute("SELECT total_debt, min_payment FROM debt_account WHERE name = ?", (args[0],))
        r = c.fetchone()
        new_min = r["total_debt"] * (r["min_payment"] / (r["total_debt"] + float(args[1]))) if (r["total_debt"] + float(args[1])) > 0 else 0
        c.execute("UPDATE debt_account SET min_payment = ? WHERE name = ?", (max(new_min, 0), args[0]))
        conn.commit()
        print(f"Pago registrado: ${float(args[1]):,.0f} a {args[0]}")
    conn.close()

def cmd_plan(args):
    """Genera plan de pago de deudas (metodo avalancha)"""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM debt_account WHERE is_active=1 ORDER BY interest_rate DESC")
    debts = c.fetchall()
    conn.close()
    if not debts:
        print("No hay deudas registradas")
        return
    print("\n=== PLAN DE PAGO (METODO AVALANCHA) ===")
    print("(Paga primero la deuda con mayor interes)\n")
    data = []
    for d in debts:
        data.append([d["name"], f"${d['total_debt']:,.0f}",
                     f"{d['interest_rate']:.1f}%", f"${d['min_payment']:,.0f}"])
    print(tabulate(data, headers=["Deuda", "Saldo", "Interes", "Pago Minimo"], tablefmt="grid"))
    total_debt = sum(d["total_debt"] for d in debts)
    total_min = sum(d["min_payment"] for d in debts)
    print(f"\n  Deuda total: ${total_debt:,.0f}")
    print(f"  Pago minimo total: ${total_min:,.0f}/mes")
    print(f"\n  ORDEN DE PAGO RECOMENDADO:")
    for i, d in enumerate(debts, 1):
        extra = "$0"
        if i == 1:
            extra = "TODO el dinero extra disponible"
        print(f"  {i}. {d['name']} (TEA: {d['interest_rate']:.1f}%) - Minimo: ${d['min_payment']:,.0f} - {extra}")

def help_menu():
    print("""
MiFinanza - Gestion Financiera Personal
========================================
COMANDOS:
  balance                    - Ver resumen del mes actual
  income <fuente> <monto> [fecha] [--recurring]
                             - Registrar ingreso
  expense <categoria> <monto> [descripcion] [fecha] [metodo_pago]
                             - Registrar gasto
  budget                     - Ver presupuesto del mes
  budget set <cat> <monto>   - Fijar presupuesto para categoria
  debts                      - Ver deudas activas
  add-debt <nombre> <total> <minimo> <dia_vence> [interes]
                             - Registrar deuda
  pay-debt <nombre> <monto>  - Pagar parte de una deuda
  plan                       - Plan de pago recomendado
  goals                      - Ver metas de ahorro
  add-goal <nombre> <monto> [fecha_limite] [prioridad=1]
                             - Crear meta de ahorro
  report                     - Reporte mensual completo
  help                       - Este menu
  init                       - Inicializar base de datos
""")

def main():
    if len(sys.argv) < 2:
        help_menu()
        return
    init_db()
    cmd = sys.argv[1]
    args = sys.argv[2:]
    cmds = {
        "help": lambda a: help_menu(),
        "init": lambda a: print("Base de datos inicializada"),
        "balance": cmd_balance,
        "income": cmd_add_income,
        "expense": cmd_add_expense,
        "budget": cmd_budget,
        "debts": cmd_debts,
        "add-debt": cmd_add_debt,
        "pay-debt": cmd_pay_debt,
        "plan": cmd_plan,
        "goals": cmd_goals,
        "add-goal": cmd_add_goal,
        "report": cmd_report,
    }
    if cmd in cmds:
        cmds[cmd](args)
    else:
        print(f"Comando desconocido: {cmd}")
        help_menu()

if __name__ == "__main__":
    main()
