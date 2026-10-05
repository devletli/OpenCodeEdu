import sys
with open("test_output.txt", "w") as f:
    f.write("hello from script\n")
    f.flush()

# Test database
import sqlite3
conn = sqlite3.connect("data/kiraci.db")
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
with open("test_output.txt", "a") as f:
    f.write(f"Tables: {tables}\n")
    f.flush()

if tables:
    for t in tables:
        cursor.execute(f"SELECT * FROM {t[0]}")
        rows = cursor.fetchall()
        with open("test_output.txt", "a") as f:
            f.write(f"{t[0]}: {rows}\n")
            f.flush()