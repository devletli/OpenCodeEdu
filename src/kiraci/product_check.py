from __future__ import annotations

import os
import re
import zipfile
from pathlib import Path

from .store import find_secret

REQUIRED_FILES = ("listing.md", "README.md", "CHECKLIST.md", "LICENSE.txt")
MAX_DELIVERABLE_BYTES = 50 * 1024 * 1024
MIN_PRICE_EUR = 3.0
MAX_PRICE_EUR = 99.0

PLACEHOLDER_RES = (
    re.compile(r"\bTODO\b", re.IGNORECASE),
    re.compile(r"\bFIXME\b", re.IGNORECASE),
    re.compile(r"lorem ipsum", re.IGNORECASE),
    re.compile(r"<placeholder>", re.IGNORECASE),
)
INCOME_PROMISE_RES = (
    re.compile(r"guaranteed", re.IGNORECASE),
    re.compile(r"get rich", re.IGNORECASE),
    re.compile(r"passive income", re.IGNORECASE),
)

DISCLOSURE_TEMPLATE = "Created and maintained by an AI agent system operated by {owner}."


def owner_name() -> str:
    return os.environ.get("KIRACI_OWNER_NAME", "") or "the store owner"


def _read_text_files(path: Path) -> tuple[list[tuple[str, str]], list[str]]:
    """Return ([(rel, text)], [unreadable rels]). Binary files are skipped."""
    texts: list[tuple[str, str]] = []
    unreadable: list[str] = []
    for p in sorted(path.rglob("*")):
        if not p.is_file() or p.suffix.lower() == ".zip":
            continue
        try:
            texts.append((str(p.relative_to(path)), p.read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError):
            continue
    return texts, unreadable


def _parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    """Parse a leading --- block. Returns (fields, body)."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    fields: dict[str, str] = {}
    for line in text[3:end].strip().splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            fields[key.strip().lower()] = value.strip().strip("\"'")
    return fields, text[end + 4:].lstrip("\n")


def _parse_price(raw: str) -> float | None:
    try:
        return float(raw.replace("€", "").replace(",", ".").strip())
    except (ValueError, AttributeError):
        return None


def check_product(path: Path | str, owner: str | None = None) -> list[str]:
    """Validate a product package. Empty list means valid."""
    path = Path(path)
    problems: list[str] = []
    if not path.is_dir():
        return [f"not a directory: {path}"]
    for name in REQUIRED_FILES:
        if not (path / name).is_file():
            problems.append(f"missing required file: {name}")
    deliverable = path / "deliverable"
    if not deliverable.is_dir():
        problems.append("missing deliverable/ directory")
        deliverable_files = []
    else:
        deliverable_files = [p for p in deliverable.rglob("*") if p.is_file()]
        if not deliverable_files:
            problems.append("deliverable/ is empty")
        else:
            total = sum(p.stat().st_size for p in deliverable_files)
            if total > MAX_DELIVERABLE_BYTES:
                problems.append(
                    f"deliverable/ too large: {total} bytes "
                    f"(max {MAX_DELIVERABLE_BYTES})")
    texts, _ = _read_text_files(path)
    by_name = dict(texts)
    listing = by_name.get("listing.md")
    if listing is not None:
        fields, body = _parse_front_matter(listing)
        for key in ("title", "price_eur", "tags"):
            if key not in fields:
                problems.append(f"listing.md front matter missing: {key}")
        price = _parse_price(fields.get("price_eur", ""))
        if price is None:
            problems.append("listing.md front matter: price_eur is not a number")
        elif not MIN_PRICE_EUR <= price <= MAX_PRICE_EUR:
            problems.append(
                f"listing.md front matter: price_eur {price} outside 3-99")
        expected = DISCLOSURE_TEMPLATE.format(owner=owner or owner_name())
        non_empty = [ln for ln in listing.splitlines() if ln.strip()]
        if not non_empty or non_empty[-1].strip() != expected:
            problems.append("listing.md must end with the disclosure line: "
                            f"{expected}")
        for rx in INCOME_PROMISE_RES:
            if rx.search(body):
                problems.append(
                    f"listing.md description makes income promises ({rx.pattern})")
                break
    for rel, text in texts:
        for rx in PLACEHOLDER_RES:
            if rx.search(text):
                problems.append(f"{rel} contains placeholder text ({rx.pattern})")
                break
        secret = find_secret(text)
        if secret:
            problems.append(f"{rel} {secret}")
    return problems


def build_dist_zip(path: Path | str) -> Path:
    """Zip deliverable/ into dist/<slug>.zip. Returns the zip path."""
    path = Path(path)
    dist = path / "dist"
    dist.mkdir(parents=True, exist_ok=True)
    zpath = dist / f"{path.name}.zip"
    deliverable = path / "deliverable"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(deliverable.rglob("*")):
            if p.is_file():
                zf.write(p, p.relative_to(deliverable))
    return zpath
