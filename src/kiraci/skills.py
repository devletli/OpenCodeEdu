from __future__ import annotations

import re
from pathlib import Path

from .store import find_secret

MAX_SKILL_CHARS = 4000
MAX_SELECT_CHARS = 6000
MAX_SELECT_FILES = 3
SKILL_NAME_RE = re.compile(r"^[a-z0-9-]{3,40}$")


def parse_front_matter(text: str) -> tuple[dict[str, object], str]:
    """Parse a leading --- block. Returns (fields, body); {} if absent."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    fields: dict[str, object] = {}
    for line in text[3:end].strip().splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            fields[key.strip().lower()] = [
                v.strip().strip("\"'") for v in value[1:-1].split(",") if v.strip()
            ]
        else:
            fields[key.strip().lower()] = value.strip("\"'")
    return fields, text[end + 4:].lstrip("\n")


def _skill_files(root: Path, sub: str) -> list[Path]:
    d = Path(root) / "skills" / sub if sub else Path(root) / "skills"
    if not d.is_dir():
        return []
    return sorted(
        (p for p in d.glob("*.md") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2}


def select_for_task(root, agent: str, title: str, prompt: str) -> str:
    """Pick up to 3 recent matching skills (+ kind-matching lessons), <=6000 chars."""
    words = _words(f"{title} {prompt}")
    picked: list[tuple[str, str]] = []
    total = 0

    def consider(path: Path, front: dict) -> None:
        nonlocal total
        if len(picked) >= MAX_SELECT_FILES:
            return
        agents = front.get("agents", [])
        if isinstance(agents, list) and agent not in agents:
            return
        tags = front.get("tags", [])
        hay = {t.lower() for t in tags if isinstance(t, str)}
        hay |= _words(str(front.get("title", "")))
        kind = front.get("venture_kind")
        overlap = bool(hay & words) or (
            isinstance(kind, str) and kind.lower() in words)
        if not overlap:
            return
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            return
        if total + len(content) > MAX_SELECT_CHARS:
            return
        picked.append((path.stem, content))
        total += len(content)

    for path in _skill_files(Path(root), ""):
        if path.parent.name == "lessons":
            continue
        try:
            front, _ = parse_front_matter(path.read_text(encoding="utf-8"))
        except OSError:
            continue
        if front:
            consider(path, front)
    for path in _skill_files(Path(root), "lessons"):
        try:
            front, _ = parse_front_matter(path.read_text(encoding="utf-8"))
        except OSError:
            continue
        if front:
            consider(path, front)
    return "\n\n".join(f"### {name}\n{content}" for name, content in picked)


def extract_skill_blocks(text: str) -> list[tuple[str, str]]:
    """Split chronicler output into (name, content) for each `SKILL: <name>` block."""
    blocks: list[tuple[str, str]] = []
    name: str | None = None
    buf: list[str] = []
    for line in (text or "").splitlines():
        if line.startswith("SKILL:"):
            if name is not None:
                blocks.append((name, "\n".join(buf).strip() + "\n"))
            name = line[len("SKILL:"):].strip()
            buf = []
        elif name is not None:
            buf.append(line)
    if name is not None:
        blocks.append((name, "\n".join(buf).strip() + "\n"))
    return blocks


def validate_skill(name: str, content: str) -> str | None:
    """Return an error reason, or None if the skill block is acceptable."""
    if not SKILL_NAME_RE.match(name or ""):
        return f"bad skill name: {name!r}"
    if not content or len(content) > MAX_SKILL_CHARS:
        return f"skill {name!r} must be 1-4000 chars"
    front, _ = parse_front_matter(content)
    if not front:
        return f"skill {name!r} has no front matter"
    secret = find_secret(content)
    if secret:
        return f"skill {name!r} {secret}"
    return None


def save_skill(root, name: str, content: str) -> str | None:
    """Save a validated skill; never overwrites. Returns error or None."""
    err = validate_skill(name, content)
    if err:
        return err
    path = Path(root) / "skills" / f"{name}.md"
    if path.exists():
        return f"skill {name!r} already exists, not overwriting"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    except OSError as e:
        return f"skill {name!r} write failed: {e}"
    return None
