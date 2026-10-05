# AGENT DIRECTIVE: System Remediation & Architecture Hardening

## ROLE & OBJECTIVE
You are an Autonomous Systems Architect & DevSecOps Engineer. Your task is to refactor, secure, and stabilize the `OpenCodeEdu` repository. You will decouple runtime state from version control, harden sandbox isolation, optimize CI/CD pipelines, and ensure ledger transaction safety.

Execute the following steps sequentially. Validate after each phase before proceeding.

---

## PHASE 1: Repository Hygiene & Decoupling State from Code

### Objective
Stop git pollution caused by continuous snapshot daemons and local state tracking (`journal/`, `research/`, `products/`, `data/`).

### Step 1.1: Update `.gitignore`
Append dynamic runtime output and database files to `.gitignore`.

```gitignore
# Dynamic Runtime Data & Agent Artifacts
/data/*
!/data/.gitkeep
/journal/*
!/journal/.gitkeep
/research/*
!/research/.gitkeep
/products/*
!/products/.gitkeep
/scripts/outputs/*

# Local Storage & Databases
*.db
*.sqlite3
*.log

# Environments
.venv/
venv/
Step 1.2: Refactor Snapshot Daemon Persistence
Update the snapshot daemon (located in .opencode/agent or src/kiraci/) to write local logs and journal artifacts to SQLite or an S3/MinIO bucket rather than executing git commit on the main branch.

Example Refactoring (src/kiraci/daemon.py):

Python
import sqlite3
import json
from pathlib import Path

DB_PATH = Path("data/state.db")

def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS daemon_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                module TEXT,
                payload JSON
            )
        """)

def save_snapshot(module: str, payload: dict):
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO daemon_snapshots (module, payload) VALUES (?, ?)",
            (module, json.dumps(payload))
        )
PHASE 2: Sandbox Hardening & Security Isolation
Objective
Eliminate sandbox escape vectors caused by sharing host PATH, virtual environments (.venv), or repository directories with untrusted execution environments.

Step 2.1: Isolate Sandbox Environment
Ensure the execution judge (src/kiraci/judge.py or tools/sandbox.py) runs user/agent code inside an ephemeral Container or isolated environment without mounting host sensitive paths (.env, root .opencode).

Example Secure Execution Pattern (tools/sandbox.py):

Python
import subprocess
import tempfile
from pathlib import Path

def run_in_sandbox(script_content: str, timeout: int = 15) -> dict:
    """Executes arbitrary code inside an isolated, non-root, read-only container."""
    with tempfile.TemporaryDirectory() as temp_dir:
        script_file = Path(temp_dir) / "submission.py"
        script_file.write_text(script_content)

        docker_cmd = [
            "docker", "run", "--rm",
            "--network", "none",
            "--memory", "256m",
            "--cpus", "0.5",
            "--user", "1000:1000",
            "-v", f"{script_file}:/app/submission.py:ro",
            "python:3.11-slim",
            "python", "/app/submission.py"
        ]

        try:
            res = subprocess.run(docker_cmd, capture_output=True, text=True, timeout=timeout)
            return {"exit_code": res.returncode, "stdout": res.stdout, "stderr": res.stderr}
        except subprocess.TimeoutExpired:
            return {"exit_code": -1, "stdout": "", "stderr": "Execution timed out."}
PHASE 3: CI/CD Optimization & Pre-commit Quality Control
Objective
Eliminate hacky PYTHONPATH workarounds in GitHub Actions and enforce linting locally before commits reach remote.

Step 3.1: Configure .pre-commit-config.yaml
Create .pre-commit-config.yaml in the repository root to catch errors (e.g., E741) locally.