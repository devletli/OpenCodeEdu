import sqlite3
import traceback

try:
    with open("check_output.txt", "w") as f:
        conn = sqlite3.connect("data/kiraci.db")
        cursor = conn.cursor()
        cursor.execute("SELECT id, title, agent, priority, status, prompt FROM tasks")
        rows = cursor.fetchall()
        f.write(f"Found {len(rows)} tasks\n")
        f.flush()
        for row in rows:
            f.write(f"ID: {row[0]}, Title: {row[1]}, Agent: {row[2]}, Priority: {row[3]}, Status: {row[4]}\n")
            f.write(f"Prompt: {row[5][:100]}...\n\n")
            f.flush()
except Exception as e:
    with open("check_error.txt", "w") as f:
        f.write(traceback.format_exc())