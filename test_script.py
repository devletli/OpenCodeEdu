import sys
print("hello")
sys.stdout.flush()

# Test database
import sqlite3
conn = sqlite3.connect("data/kiraci.db")
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
print(f"Tables: {tables}")

if tables:
    for t in tables:
        cursor.execute(f"SELECT * FROM {t[0]}")
        rows = cursor.fetchall()
        print(f"{t[0]}: {rows}")