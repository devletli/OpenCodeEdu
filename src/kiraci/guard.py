from __future__ import annotations

ALLOWED_PREFIXES = (
    "products/", "tools/", "skills/", "research/", "journal/", "people/", "personas/",
)


def parse_raw_diff(text: str) -> list[tuple[str, str, str]]:
    """Parse `git diff --raw --no-renames <base> <head>` into (status, path, mode)."""
    out: list[tuple[str, str, str]] = []
    for line in text.splitlines():
        if not line.startswith(":"):
            continue
        meta, _, path = line.partition("\t")
        parts = meta[1:].split()
        old_mode, new_mode, status = parts[0], parts[1], parts[4][0]
        out.append((status, path, old_mode if status == "D" else new_mode))
    return out


def violations(changes: list[tuple[str, str, str]]) -> list[str]:
    bad: list[str] = []
    for status, path, mode in changes:
        parts = path.split("/")
        if path.startswith(('"', "/")) or ".." in parts or "" in parts:
            bad.append(f"suspicious path: {path}")
        elif not path.startswith(ALLOWED_PREFIXES):
            bad.append(f"outside allowed area: {path}")
        elif mode in ("120000", "160000"):
            bad.append(f"symlink or submodule not allowed: {path}")
    return bad
