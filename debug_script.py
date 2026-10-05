import sys
import traceback

print("Starting script...", flush=True)
sys.stdout.flush()

with open("debug_output.txt", "w") as f:
    f.write("Script started\n")
    f.flush()

try:
    import sqlite3
    with open("debug_output.txt", "a") as f:
        f.write("sqlite3 imported\n")
        f.flush()
    
    conn = sqlite3.connect("data/kiraci.db")
    with open("debug_output.txt", "a") as f:
        f.write("Connected to DB\n")
        f.flush()
    
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, agent, priority, status FROM tasks")
    rows = cursor.fetchall()
    
    with open("debug_output.txt", "a") as f:
        f.write(f"Found {len(rows)} tasks\n")
        for row in rows:
            f.write(f"ID: {row[0]}, Title: {row[1]}, Agent: {row[2]}, Priority: {row[3]}, Status: {row[4]}\n")
        f.flush()
        
except Exception as e:
    with open("debug_error.txt", "w") as f:
        f.write(traceback.format_exc())
    with open("debug_output.txt", "a") as f:
        f.write(f"Exception: {e}\n")
        f.flush()

print("Script done", flush=True)