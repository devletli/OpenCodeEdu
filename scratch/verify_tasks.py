import sqlite3

with open("verify_output.txt", "w") as f:
    f.write("Verifying tasks...\n")
    f.flush()

try:
    conn = sqlite3.connect("data/kiraci.db")
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, title, agent, priority, status, prompt FROM tasks")
    rows = cursor.fetchall()
    
    with open("verify_output.txt", "a") as f:
        f.write(f"Found {len(rows)} tasks\n\n")
        for row in rows:
            f.write(f"ID: {row[0]}\n")
            f.write(f"Title: {row[1]}\n")
            f.write(f"Agent: {row[2]}\n")
            f.write(f"Priority: {row[3]}\n")
            f.write(f"Status: {row[4]}\n")
            f.write(f"Prompt: {row[5][:200]}...\n")
            f.write("-" * 80 + "\n\n")
        f.flush()
    
    conn.close()
    
except Exception as e:
    with open("verify_error.txt", "w") as f:
        import traceback
        f.write(traceback.format_exc())

with open("verify_output.txt", "a") as f:
    f.write("Done\n")
    f.flush()