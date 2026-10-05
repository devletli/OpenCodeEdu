import sqlite3
import uuid
from datetime import datetime, UTC

with open("debug_output2.txt", "w") as f:
    f.write("Starting insert...\n")
    f.flush()

try:
    conn = sqlite3.connect("data/kiraci.db")
    cursor = conn.cursor()
    
    with open("debug_output2.txt", "a") as f:
        f.write("Connected to DB\n")
        f.flush()
    
    tasks = [
        {
            'title': '[revenue] Research: Niche digital product opportunities (templates, prompt packs, tool packs)',
            'agent': 'scout',
            'priority': 10,
            'prompt': '''Research and identify 20+ niche digital product opportunities in these categories:
1. Templates (Notion, Excel, Google Sheets, Airtable)
2. Prompt packs (for LLMs, Midjourney, Stable Diffusion, etc.)
3. Small Python tool packs (CLI tools, automation scripts, data processing)

For each opportunity, score using this formula:
Score = (Demand Signals * 0.4) + (Competition Gap * 0.3) + (Production Effort * 0.2) + (Margin Potential * 0.1)

Where:
- Demand Signals: Search volume, Reddit/discord mentions, marketplace sales, Google Trends (0-100)
- Competition Gap: Inverse of # of existing products, review saturation (0-100)  
- Production Effort: Inverse of hours to create + maintain (0-100)
- Margin Potential: Price point * (1 - platform_fee) / effort (0-100)

Output: JSON list of opportunities with scores, sources (URLs), and reasoning. Narrow to top 3 with highest scores.'''
        },
        {
            'title': '[revenue] Research: Open source bounty opportunities (Algora, GitHub bounties)',
            'agent': 'scout',
            'priority': 8,
            'prompt': '''Research open source bounty platforms and opportunities:
1. Algora (algora.com) - search for bounties matching our skills (Python, automation, CLI tools, templates)
2. GitHub Sponsors / GitHub Bounties - find repositories with active bounties
3. Other platforms: Bountysource, IssueHunt, Polar.sh, OpenCollective

For each platform/opportunity, score using:
Score = (Bounty Amount * 0.3) + (Skill Match * 0.3) + (Time to Complete * 0.2) + (Recurring Potential * 0.2)

Where:
- Bounty Amount: USD value (0-100 normalized)
- Skill Match: How well our stack matches (Python, automation, templates, prompts) (0-100)
- Time to Complete: Inverse of estimated hours (0-100)
- Recurring Potential: Chance of repeat work / retainer (0-100)

Output: JSON list with platform, bounty details, scores, application links. Focus on bounties $100-$2000.'''
        },
        {
            'title': '[revenue] Research: Niche research report opportunities (10-20 page PDFs)',
            'agent': 'scout',
            'priority': 6,
            'prompt': '''Research opportunities for selling niche research reports (10-20 page PDFs) on specific sectors:
1. Industry trends reports (AI in X, automation in Y, no-code in Z)
2. Market sizing / TAM analysis for niche markets
3. Competitive landscape analyses
4. Technology adoption curves for specific verticals
5. Regulatory/compliance guides for niche industries

Score each using:
Score = (Willingness to Pay * 0.35) + (Search Demand * 0.25) + (Data Accessibility * 0.2) + (Production Effort * 0.2)

Where:
- Willingness to Pay: Evidence of buyers (Gumroad, Leanpub, niche marketplaces) (0-100)
- Search Demand: Keyword volume, "buy research report X" queries (0-100)
- Data Accessibility: Public data sources, APIs, scrapable sources (0-100)
- Production Effort: Inverse of research + writing hours (0-100)

Output: JSON list of 15+ report topics with scores, target audience, price point estimates, data sources. Narrow to top 3.'''
        }
    ]

    for task in tasks:
        task_id = str(uuid.uuid4())
        created_at = datetime.now(UTC).isoformat()
        cursor.execute("""
            INSERT INTO tasks (id, title, agent, priority, status, prompt, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'pending', ?, ?, ?)
        """, (task_id, task['title'], task['agent'], task['priority'], task['prompt'], created_at, created_at))
        
        with open("debug_output2.txt", "a") as f:
            f.write(f"Inserted task: {task['title']}\n")
            f.flush()

    conn.commit()
    
    with open("debug_output2.txt", "a") as f:
        f.write("Commit done\n")
        f.flush()
    
    # Verify
    cursor.execute("SELECT id, title, agent, priority, status FROM tasks")
    rows = cursor.fetchall()
    
    with open("debug_output2.txt", "a") as f:
        f.write(f"Found {len(rows)} tasks\n")
        for row in rows:
            f.write(f"ID: {row[0]}, Title: {row[1]}, Agent: {row[2]}, Priority: {row[3]}, Status: {row[4]}\n")
        f.flush()
    
    conn.close()
    
except Exception as e:
    with open("debug_error2.txt", "w") as f:
        import traceback
        f.write(traceback.format_exc())
    with open("debug_output2.txt", "a") as f:
        f.write(f"Exception: {e}\n")
        f.flush()

with open("debug_output2.txt", "a") as f:
    f.write("Script done\n")
    f.flush()