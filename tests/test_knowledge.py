"""Knowledge layer: index parsing, domain matching, example search and saving."""

import json

import pytest

from cadkit import knowledge as kb


def test_index_lists_every_domain_file(kb_copy):
    domains = kb.list_domains()
    files = {d["file"] for d in domains}
    on_disk = {p.name for p in (kb_copy / "domains").glob("*.md") if not p.name.startswith("_")}
    assert files == on_disk, "every domain file must be in _index.md and vice versa"
    assert len(domains) >= 7


def test_every_domain_follows_the_template(kb_copy):
    required = [
        "Reality check",
        "Ask the user first",
        "calculations",
        "Verification",
        "Standards",
        "Manufactur",
        "FreeCAD",
        "honest",
    ]
    for d in kb.list_domains():
        text = (kb_copy / "domains" / d["file"]).read_text(encoding="utf-8")
        missing = [r for r in required if r.lower() not in text.lower()]
        assert not missing, f"{d['file']} is missing sections: {missing}"


@pytest.mark.parametrize(
    "request_text, expected",
    [
        ("design a 2-person catamaran hull", "boat-building-lsam.md"),
        ("spur gear pair with module 2, ratio 3:1", "gears-power-transmission.md"),
        ("L bracket from 2 mm sheet metal with one bend", "sheet-metal.md"),
        ("welded frame from SHS 40x40", "weldments.md"),
        ("M6 counterbore holes on a bolt pattern", "fasteners-fits.md"),
        ("stepped shaft with a keyway and two ball bearings", "shafts-bearings.md"),
        ("PETG phone stand I can 3D print", "fdm-3d-printing.md"),
        ("flange OD 120, six M8 holes on a 90 mm pitch circle", "fasteners-fits.md"),
        ("FEA of the bracket: von Mises stress and deflection", "fea-mechanics.md"),
    ],
)
def test_match_domain_top_hit(kb_copy, request_text, expected):
    res = kb.match_domain(request_text)
    assert res["matches"] and res["matches"][0]["file"] == expected, res


def test_match_domain_none(kb_copy):
    res = kb.match_domain("make a 20 x 10 x 5 box")
    assert res["matches"] == [] and res["advice"].startswith("none")


def test_match_domain_no_partial_word_hits(kb_copy):
    # 'gearing' should not trigger via substring of 'gear'? it may (plural/ing); but
    # 'keyboard' must NOT trigger 'key', and 'bolted' must not trigger shafts.
    res = kb.match_domain("keyboard tray")
    assert all(m["file"] != "shafts-bearings.md" for m in res["matches"])


def test_search_examples_ranks_obvious_match_first(kb_copy):
    hits = kb.search_examples("plate with two mounting holes and a post")
    assert hits[0]["file"] == "plate_with_holes.md"
    hits = kb.search_examples("3 to 1 spur gear pair")
    assert hits[0]["file"] == "spur_pair_3to1.md"


def test_read_doc_blocks_path_escape(kb_copy):
    with pytest.raises(ValueError):
        kb.read_doc("../server.py")
    assert "conventions" in kb.read_doc("conventions.md").lower()


def test_save_example_roundtrip(kb_copy):
    code = "import Part\nresult = Part.makeBox(1, 2, 3).Volume\n"
    res = kb.save_example(
        "Tiny box", "make a 1x2x3 box", code, ["which size?"], domain="general", metrics={"volume_mm3": 6.0}
    )
    path = kb_copy / "examples" / "tiny_box.md"
    text = path.read_text(encoding="utf-8")
    assert '**Prompt it answers:** "make a 1x2x3 box"' in text
    assert "```python" in text and "volume_mm3 = 6.0" in text
    # it is now searchable and listed
    assert kb.search_examples("1x2x3 box")[0]["file"] == "tiny_box.md"
    assert any(e["file"] == "tiny_box.md" for e in kb.list_examples())
    with pytest.raises(FileExistsError):
        kb.save_example("Tiny box", "again", code)
    assert res["slug"] == "tiny_box"


def test_log_correction_and_stats(kb_copy):
    kb.log_correction("bracket", "holes too close to edge", "moved to 2d", domain="sheet-metal")
    kb.log_correction("hull", "freeboard too low", "raised sheer", domain="boat-building-lsam")
    kb.log_correction("hull 2", "GM negative", "wider beam", domain="boat-building-lsam")
    st = kb.correction_stats()
    assert st["corrections"] == 3 and st["by_domain"]["boat-building-lsam"] == 2
    line = (kb_copy / "corrections.jsonl").read_text(encoding="utf-8").splitlines()[0]
    assert json.loads(line)["wrong"] == "holes too close to edge"


@pytest.fixture
def layered(tmp_path, monkeypatch):
    """A public and a private knowledge folder, private layered on top."""
    public, private = tmp_path / "public", tmp_path / "private"
    for base, body in ((public, "public plate"), (private, "private plate")):
        (base / "examples").mkdir(parents=True)
        (base / "examples" / "plate.md").write_text(f"# Example: {body}\n", encoding="utf-8")
    (public / "examples" / "shaft.md").write_text("# Example: public shaft\n", encoding="utf-8")
    monkeypatch.setattr(kb, "ROOT", public)
    monkeypatch.setattr(kb, "EXTRA_ROOTS", [private])
    return public, private


def test_private_examples_override_public_ones_with_the_same_name(layered):
    titles = {e["file"]: e["title"] for e in kb.list_examples()}
    assert titles == {"plate.md": "Example: private plate", "shaft.md": "Example: public shaft"}
    assert "private plate" in kb.read_doc("examples/plate.md")


def test_new_examples_and_corrections_go_to_the_private_folder(layered):
    public, private = layered
    kb.save_example("Bracket", "an L bracket", "result = 1")
    kb.log_correction("an L bracket", "holes too close", "moved holes")
    assert (private / "examples" / "bracket.md").exists()
    assert (private / "corrections.jsonl").exists()
    assert not (public / "examples" / "bracket.md").exists()
