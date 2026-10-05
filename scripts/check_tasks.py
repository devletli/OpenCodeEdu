import sqlite3

conn = sqlite3.connect('data/kiraci.db')
cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='human_tasks'")
result = cursor.fetchone()
print(f"Table exists: {result}")

if result:
    cursor = conn.execute("SELECT COUNT(*) FROM human_tasks")
    count = cursor.fetchone()[0]
    print(f"Count: {count}")
    
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM human_tasks").fetchall()
    for row in rows:
        print(dict(row))

conn.close()
