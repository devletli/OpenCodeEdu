import sqlite3

conn = sqlite3.connect("data/kiraci.db")
cursor = conn.cursor()
cursor.execute("SELECT id, title, agent, priority, status, prompt FROM tasks")
rows = cursor.fetchall()
for row in rows:
    print(f"ID: {row[0]}, Title: {row[1]}, Agent: {row[2]}, Priority: {row[3]}, Status: {row[4]}")
    print(f"Prompt: {row[5][:100]}...")
    print()