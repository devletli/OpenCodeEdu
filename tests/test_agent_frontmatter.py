"""Agent frontmatter explicitness (Phase 3).

Every agent file must spell out its tool booleans (no silent defaults),
deny-by-default bash access where bash is on, and never carry a `model:`
line. Path denial (data/, .env, *.db) is not expressible in frontmatter;
it lives in the sandbox mounts + guard.py, tested elsewhere.
"""

from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parent.parent / ".opencode" / "agent"

EXPECTED_AGENTS = {"brain", "scout", "builder", "seller", "treasurer",
                   "diplomat", "judge", "chronicler"}


def _front(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), path
    front = text.split("---", 2)[1]
    root: dict = {}
    stack: list[tuple[int, dict]] = [(-1, root)]
    for raw in front.splitlines():
        if not raw.strip():
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        key, _, val = raw.strip().partition(":")
        key = key.strip('"').strip("'")
        val = val.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        node: dict = {} if val == "" else _scalar(val)
        stack[-1][1][key] = node
        if isinstance(node, dict):
            stack.append((indent, node))
    return root


def _scalar(val: str):
    if val == "true":
        return True
    if val == "false":
        return False
    return val.strip('"').strip("'")


def _agents():
    files = sorted(AGENT_DIR.glob("*.md"))
    assert {p.stem for p in files} == EXPECTED_AGENTS
    return files


def test_tool_booleans_explicit_everywhere():
    for path in _agents():
        tools = _front(path).get("tools", {})
        for flag in ("write", "edit", "bash", "webfetch"):
            assert tools.get(flag) in (True, False), (path.name, flag)


def test_bash_enabled_means_default_deny():
    for path in _agents():
        front = _front(path)
        if front.get("tools", {}).get("bash") is True:
            bash = front.get("permission", {}).get("bash", {})
            assert bash.get("*") == "deny", path.name


def test_no_model_lines():
    for path in _agents():
        for line in path.read_text(encoding="utf-8").splitlines():
            assert not line.startswith("model:"), path.name


def test_description_and_mode_present():
    for path in _agents():
        front = _front(path)
        assert front.get("description"), path.name
        assert front.get("mode") in ("primary", "all"), path.name
