import pytest

from kiraci import product_check

DISCLOSURE = ("Created and maintained by an AI agent system "
              "operated by the store owner.")


@pytest.fixture
def pkg(tmp_path, monkeypatch):
    monkeypatch.delenv("KIRACI_OWNER_NAME", raising=False)
    d = tmp_path / "pkg"
    (d / "deliverable").mkdir(parents=True)
    (d / "listing.md").write_text(
        "---\ntitle: Widget Pack\nprice_eur: 9.99\ntags: [widgets]\n---\n"
        "A useful pack of widgets for your project.\n"
        f"{DISCLOSURE}\n",
        encoding="utf-8")
    (d / "README.md").write_text("# Widget Pack\nUse it well.\n", encoding="utf-8")
    (d / "CHECKLIST.md").write_text("- [x] Done\n", encoding="utf-8")
    (d / "LICENSE.txt").write_text("All rights reserved.\n", encoding="utf-8")
    (d / "deliverable" / "widgets.zip").write_bytes(b"0" * 100)
    return d


def test_valid_package_passes(pkg):
    assert product_check.check_product(pkg) == []


@pytest.mark.parametrize("missing", ["listing.md", "README.md", "CHECKLIST.md",
                                     "LICENSE.txt"])
def test_each_missing_file_is_a_problem(pkg, missing):
    (pkg / missing).unlink()
    problems = product_check.check_product(pkg)
    assert any(missing in p for p in problems)


def test_empty_deliverable_is_a_problem(pkg):
    (pkg / "deliverable" / "widgets.zip").unlink()
    assert any("deliverable" in p for p in product_check.check_product(pkg))


def test_oversize_deliverable_is_a_problem(pkg, monkeypatch):
    monkeypatch.setattr(product_check, "MAX_DELIVERABLE_BYTES", 10)
    assert any("too large" in p for p in product_check.check_product(pkg))


@pytest.mark.parametrize("price", ["2.99", "100", "free"])
def test_bad_price_is_a_problem(pkg, price):
    text = (pkg / "listing.md").read_text(encoding="utf-8")
    text = text.replace("price_eur: 9.99", f"price_eur: {price}")
    (pkg / "listing.md").write_text(text, encoding="utf-8")
    assert any("price_eur" in p for p in product_check.check_product(pkg))


@pytest.mark.parametrize("marker", ["TODO: fix this", "FIXME later",
                                    "lorem ipsum dolor", "<placeholder>"])
def test_placeholder_text_is_a_problem(pkg, marker):
    with (pkg / "README.md").open("a", encoding="utf-8") as f:
        f.write(marker + "\n")
    assert any("placeholder" in p for p in product_check.check_product(pkg))


def test_secret_string_is_a_problem(pkg):
    with (pkg / "README.md").open("a", encoding="utf-8") as f:
        f.write("key: sk-proj-abcdefgh12345678\n")
    assert any("API key" in p for p in product_check.check_product(pkg))


def test_missing_disclosure_is_a_problem(pkg):
    text = (pkg / "listing.md").read_text(encoding="utf-8")
    (pkg / "listing.md").write_text(text.replace(DISCLOSURE + "\n", ""),
                                    encoding="utf-8")
    assert any("disclosure" in p for p in product_check.check_product(pkg))


@pytest.mark.parametrize("phrase", ["guaranteed income", "GET RICH fast",
                                    "earn passive income"])
def test_income_promises_rejected(pkg, phrase):
    text = (pkg / "listing.md").read_text(encoding="utf-8")
    text = text.replace(DISCLOSURE, f"{phrase}\n{DISCLOSURE}")
    (pkg / "listing.md").write_text(text, encoding="utf-8")
    problems = product_check.check_product(pkg)
    assert any("income promises" in p for p in problems)


def test_owner_name_from_env(pkg, monkeypatch):
    monkeypatch.setenv("KIRACI_OWNER_NAME", "Jane")
    text = (pkg / "listing.md").read_text(encoding="utf-8")
    text = text.replace(
        DISCLOSURE,
        "Created and maintained by an AI agent system operated by Jane.")
    (pkg / "listing.md").write_text(text, encoding="utf-8")
    assert product_check.check_product(pkg) == []


def test_zip_built_from_deliverable(pkg):
    zpath = product_check.build_dist_zip(pkg)
    assert zpath == pkg / "dist" / "pkg.zip"
    assert zpath.exists()
    import zipfile

    with zipfile.ZipFile(zpath) as zf:
        assert zf.namelist() == ["widgets.zip"]
