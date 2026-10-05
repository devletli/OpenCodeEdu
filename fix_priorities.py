import sqlite3

conn = sqlite3.connect("data/kiraci.db")
cursor = conn.cursor()

# Update priorities
cursor.execute("UPDATE tasks SET priority = 10 WHERE id = 1")
cursor.execute("UPDATE tasks SET priority = 8 WHERE id = 2")
cursor.execute("UPDATE tasks SET priority = 6 WHERE id = 3")

conn.commit()

# Verify
cursor.execute("SELECT id, title, agent, priority, status FROM tasks")
rows = cursor.fetchall()
for row in rows:
    print(f"ID: {row[0]}, Title: {row[1]}, Agent: {row[2]}, Priority: {row[3]}, Status: {row[4]}")

conn.close()