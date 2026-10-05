import sqlite3

conn = sqlite3.connect('data/kiraci.db')
conn.row_factory = sqlite3.Row

rows = conn.execute('SELECT id, kind, title, status, dedupe_key, created_by FROM human_tasks').fetchall()

print(f"Total human tasks: {len(rows)}")
print("-" * 80)
for r in rows:
    print(f"ID: {r['id']}, Kind: {r['kind']}, Status: {r['status']}, Key: {r['dedupe_key']}, By: {r['created_by']}")
    print(f"  Title: {r['title']}")
print("-" * 80)

conn.close()
