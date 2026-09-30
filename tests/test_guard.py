from kiraci.guard import ALLOWED_PREFIXES, parse_raw_diff, violations

SAMPLE_RAW = (
    ":100644 100644 aaa111 bbb222 M\ttools/helper.py\n"
    ":000000 100644 0000000 ccc333 A\tproducts/drafts/1-idea.md\n"
    ":100644 000000 ddd444 0000000 D\tsrc/kiraci/ledger.py\n"
)


def test_allowed_paths_pass():
    changes = [
        ("M", "tools/helper.py", "100644"),
        ("A", "products/drafts/1-idea.md", "100644"),
        ("M", "skills/research-template.md", "100644"),
        ("A", "research/2026-01-01-2-x.md", "100644"),
        ("M", "journal/2026-01-01.md", "100644"),
        ("A", "people/drafts/3-y.md", "100644"),
        ("M", "personas/scout.md", "100644"),
        ("D", "tools/old.py", "100644"),
    ]
    assert violations(changes) == []
    assert ALLOWED_PREFIXES


def test_core_paths_are_violations():
    for path in ("src/x.py", "src/kiraci/ledger.py", "tests/test_x.py",
                 "KIRACI.md", ".opencode/agent/judge.md", "deploy/kiraci.service",
                 "opencode.json", "config.toml", "data/kiraci.db", "README.md"):
        assert violations([("M", path, "100644")]), path


def test_suspicious_paths_are_violations():
    assert violations([("M", "../x.py", "100644")])
    assert violations([("M", "/etc/passwd", "100644")])
    assert violations([("M", "tools//x.py", "100644")])
    assert violations([("M", '"quo\\303\\244ted.py"', "100644")])


def test_symlink_and_submodule_modes_are_violations():
    assert violations([("A", "tools/link", "120000")])
    assert violations([("A", "tools/vendor", "160000")])


def test_deletion_of_protected_file_is_violation():
    assert violations([("D", "src/kiraci/ledger.py", "100644")])


def test_parse_raw_diff_sample():
    parsed = parse_raw_diff(SAMPLE_RAW)
    assert parsed == [
        ("M", "tools/helper.py", "100644"),
        ("A", "products/drafts/1-idea.md", "100644"),
        ("D", "src/kiraci/ledger.py", "100644"),
    ]
    bad = violations(parsed)
    assert len(bad) == 1 and "src/kiraci/ledger.py" in bad[0]


def test_parse_raw_diff_ignores_non_raw_lines():
    text = "diff --git a/tools/a.py b/tools/a.py\n" + SAMPLE_RAW.splitlines()[0]
    assert parse_raw_diff(text) == [("M", "tools/helper.py", "100644")]
