import sqlite3, os

BASE = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(BASE, "data", "myfinance", "MyFinance.db")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()
for name, sql in tables:
    print(f"Table: {name}")
    print(sql)
conn.close()
