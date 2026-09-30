from kiraci import skills


def _skill(root, name, agents, tags, title, body="Useful method."):
    (root / "skills").mkdir(exist_ok=True)
    (root / "skills" / f"{name}.md").write_text(
        f"---\ntitle: {title}\nagents: [{', '.join(agents)}]\n"
        f"tags: [{', '.join(tags)}]\n---\n\n{body}\n",
        encoding="utf-8")


def test_selection_by_agent_and_tags(tmp_path):
    _skill(tmp_path, "niche-research", ["scout"], ["research", "demand"],
           "Niche research checklist")
    _skill(tmp_path, "build-pattern", ["builder"], ["build"], "Build pattern")
    out = skills.select_for_task(tmp_path, "scout", "Research demand for widgets",
                                 "find demand signals")
    assert "niche-research" in out and "build-pattern" not in out


def test_char_cap_excludes_big_files(tmp_path):
    _skill(tmp_path, "small", ["scout"], ["research"], "Small", body="x" * 100)
    _skill(tmp_path, "big", ["scout"], ["research"], "Big", body="y" * 7000)
    out = skills.select_for_task(tmp_path, "scout", "research things", "research")
    assert "small" in out and "big" not in out


def test_lessons_included_when_kind_matches(tmp_path):
    lessons = tmp_path / "skills" / "lessons"
    lessons.mkdir(parents=True)
    (lessons / "1-dead-pack.md").write_text(
        "---\ntitle: Lesson\nagents: [scout, builder]\ntags: [lessons]\n"
        "venture_kind: bounty\n---\n\nBounties need tests.\n",
        encoding="utf-8")
    out = skills.select_for_task(tmp_path, "scout", "Find bounty work",
                                 "bounty hunting")
    assert "Bounties need tests" in out
    out2 = skills.select_for_task(tmp_path, "scout", "Research demand",
                                  "demand signals")
    assert "Bounties need tests" not in out2


def test_extract_skill_blocks():
    text = ("Intro\nSKILL: my-skill\n---\ntitle: T\n---\nBody here.\n"
            "SKILL: second-one\nContent two.\nTrailing.")
    blocks = skills.extract_skill_blocks(text)
    assert [n for n, _ in blocks] == ["my-skill", "second-one"]
    assert "Body here" in blocks[0][1]


def test_save_validates_and_never_overwrites(tmp_path):
    good = "---\ntitle: T\nagents: [scout]\ntags: [x]\n---\n\nBody.\n"
    assert skills.save_skill(tmp_path, "fresh", good) is None
    assert (tmp_path / "skills" / "fresh.md").exists()
    assert skills.save_skill(tmp_path, "fresh", good) is not None
    assert skills.save_skill(tmp_path, "Nope", good) is not None
    assert skills.save_skill(tmp_path, "ab", good) is not None
    assert skills.save_skill(tmp_path, "plain", "no front matter") is not None
    assert skills.save_skill(tmp_path, "big", "---\ntitle: T\n---\n" + "z" * 5000) \
        is not None
    assert skills.save_skill(tmp_path, "leaky", good + "sk-proj-abcdefgh12345678\n") \
        is not None
