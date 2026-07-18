import sqlite3, os

BASE = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(BASE, "data", "myfinance", "MyFinance.db")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
query = """
SELECT t.date, t.amountInDefaultCurrency, t.comment, c.title as category_title
FROM "transaction" t
LEFT JOIN sync_link sl ON t.uid = sl.entityUid AND sl.entityType = 'transaction' AND sl.otherType = 'category'
LEFT JOIN category c ON sl.otherUid = c.uid
WHERE t.isRemoved = 0
LIMIT 10;
"""
cursor.execute(query)
rows = cursor.fetchall()
print("MyFinance transactions sample:")
for r in rows:
    print(r)
conn.close()
