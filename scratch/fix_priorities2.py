import sqlite3

with open("fix_output.txt", "w") as f:
    f.write("Starting fix...\n")
    f.flush()

try:
    conn = sqlite3.connect("data/kiraci.db")
    cursor = conn.cursor()
    
    cursor.execute("UPDATE tasks SET priority = 10 WHERE id = 1")
    cursor.execute("UPDATE tasks SET priority = 8 WHERE id = 2")
    cursor.execute("UPDATE tasks SET priority = 6 WHERE id = 3")
    
    with open("fix_output.txt", "a") as f:
        f.write(f"Rows updated: {cursor.rowcount}\n")
        f.flush()
    
    conn.commit()
    
    cursor.execute("SELECT id, title, agent, priority, status FROM tasks")
    rows = cursor.fetchall()
    
    with open("fix_output.txt", "a") as f:
        f.write(f"Found {len(rows)} tasks\n")
        for row in rows:
            f.write(f"ID: {row[0]}, Title: {row[1]}, Agent: {row[2]}, Priority: {row[3]}, Status: {row[4]}\n")
        f.flush()
    
    conn.close()
    
except Exception as e:
    with open("fix_error.txt", "w") as f:
        import traceback
        f.write(traceback.format_exc())
    with open("fix_output.txt", "a") as f:
        f.write(f"Exception: {e}\n")
        f.flush()

with open("fix_output.txt", "a") as f:
    f.write("Script done\n")
    f.flush()