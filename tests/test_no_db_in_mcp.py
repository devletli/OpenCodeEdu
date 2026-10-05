"""Single-writer discipline (Phase 2): agent surfaces never touch SQLite.

MCP servers are thin IPC clients; agent prompt dirs contain no database
access. The broker (orchestrator side) is the only path that opens the DB.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

FORBIDDEN = ("sqlite3", "sqlite3.connect", ".db", "BEGIN IMMEDIATE")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_mcp_servers_never_touch_the_db():
    for name in ("src/kiraci/mcp_server.py", "src/kiraci/queue_mcp.py"):
        text = _text(ROOT / name)
        for token in FORBIDDEN:
            assert token not in text, f"{name} contains {token!r}"


def test_agent_dirs_never_touch_the_db():
    agent_dir = ROOT / ".opencode" / "agent"
    assert agent_dir.is_dir()
    hits = [p.name for p in sorted(agent_dir.glob("*.md"))
            if "sqlite3" in _text(p)]
    assert hits == []
