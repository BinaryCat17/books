"""One loader, one identity check, three trait states -- and each can fail.

Six directory parsers and three same-book checks became `datasets.bench`.
What they had learnt is kept here as checks: a foreign json is refused,
not scored; a page directory with no snapshot is refused by `Run.open` and
taken by `Run.bare` only, which then says NOT CHECKED; a trait the file does
not name is "not said", never "no".
"""
import json
import os
import tempfile

import support
from booksmith.core.errors import Unmeasurable
from booksmith.core import page
from booksmith.datasets import bench


def _page(i, blocks=(), meta=None):
    return {"index": i, "width": 100, "height": 100, "dpi": 72.0,
            "blocks": list(blocks), "raw": None, "meta": meta or {}}


LABEL = "PP-DocLayoutV2"


def _bench(root, sha="ab" * 32, pages=None, run_sha=None, label=LABEL):
    os.makedirs(os.path.join(root, "truth"))
    for i, p in enumerate(pages or [_page(0), _page(1, meta={"order_marked": True}),
                                    _page(2, meta={"text_marked": False})]):
        with open(os.path.join(root, "truth", f"{i:04d}.json"), "w") as f:
            json.dump(p, f)
    with open(os.path.join(root, "manifest.json"), "w") as f:
        json.dump({"book": os.path.basename(root),
                   "source": {"name": "x.pdf", "sha256": sha}}, f)
    # A RUN LIVES UNDER THE MODEL'S NAME. The fixture used to make
    # `detect/pages`, which was the whole layout when a book held one run;
    # a book holds one per model now, and "the run" is only defined when
    # there is exactly one.
    run = os.path.join(root, "detect", label)
    os.makedirs(os.path.join(run, "pages"))
    for i in range(3):
        with open(os.path.join(run, "pages", f"{i:04d}.json"), "w") as f:
            json.dump(_page(i), f)
    with open(os.path.join(run, "run.json"), "w") as f:
        json.dump({"source": {"path": "x.pdf", "sha256": run_sha or sha},
                   "policy": {"vocabulary": "PP-DocLayoutV2"}}, f)
    return root


def test_a_bench_opens_from_its_root_and_from_its_truth():
    with tempfile.TemporaryDirectory() as d:
        root = _bench(os.path.join(d, "b"))
        a = bench.Bench.open(root)
        b = bench.Bench.open(os.path.join(root, "truth"))
        assert a.name == b.name == "b"
        assert a.sha256 == "ab" * 32 and a.pdf is None
        assert a.runs() == [LABEL]
        assert len(a.pages()) == 3


def test_a_directory_without_truth_is_not_a_bench():
    with tempfile.TemporaryDirectory() as d:
        try:
            bench.Bench.open(d)
        except Unmeasurable as e:
            assert "truth/" in str(e)
        else:
            raise AssertionError("an empty directory opened as a bench")


def test_a_run_opens_from_its_directory_and_its_pages():
    with tempfile.TemporaryDirectory() as d:
        root = _bench(os.path.join(d, "b"))
        r = bench.Run.open(os.path.join(root, "detect", LABEL))
        s = bench.Run.open(os.path.join(root, "detect", LABEL, "pages"))
        assert r.pages_dir == s.pages_dir and r.label == s.label == LABEL
        assert r.sha256 == "ab" * 32 and r.vocabulary == "PP-DocLayoutV2"
        assert r.derived_from is None


def test_a_page_directory_without_a_snapshot_is_refused_unless_taken_bare():
    with tempfile.TemporaryDirectory() as d:
        root = _bench(os.path.join(d, "b"))
        try:
            bench.Run.open(os.path.join(root, "truth"))
        except Unmeasurable as e:
            assert "snapshot" in str(e)
        else:
            raise AssertionError("a bare page directory opened as a run")
        r = bench.Run.bare(os.path.join(root, "truth"))
        assert r.run_dir is None and r.label == "truth"
        note = bench.same_book(bench.Bench.open(root), r)
        assert note.startswith("sha256 not checked: no manifest.json or run.json"), note


def test_same_book_checks_by_sha256_and_refuses_another_book():
    with tempfile.TemporaryDirectory() as d:
        root = _bench(os.path.join(d, "b"))
        b = bench.Bench.open(root)
        assert bench.same_book(b, b.run()) == "sha256 checked: " + "ab" * 6
        other = _bench(os.path.join(d, "c"), run_sha="cd" * 32)
        try:
            bench.same_book(bench.Bench.open(other), bench.Bench.open(other).run())
        except Unmeasurable as e:
            assert "DIFFERENT books" in str(e)
        else:
            raise AssertionError("two books scored against each other in silence")


def test_same_book_says_when_the_field_is_absent():
    with tempfile.TemporaryDirectory() as d:
        root = _bench(os.path.join(d, "b"))
        with open(os.path.join(root, "detect", LABEL, "run.json"), "w") as f:
            json.dump({"source": {}}, f)
        b = bench.Bench.open(root)
        assert bench.same_book(b, b.run()).startswith(
            "sha256 not checked: the field is absent")


def test_a_foreign_json_is_refused_not_scored():
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "0000.json"), "w") as f:
            json.dump({"hello": "world"}, f)
        try:
            page.load_pages(d)
        except Unmeasurable as e:
            assert "does not look like a markup page" in str(e)
        else:
            raise AssertionError("a foreign json loaded as a page")
        try:
            page.load_pages(os.path.join(d, "nowhere"))
        except Unmeasurable as e:
            assert "no directory" in str(e)
        else:
            raise AssertionError("a missing directory loaded as pages")


def test_traits_have_three_states_and_absence_is_not_no():
    with tempfile.TemporaryDirectory() as d:
        b = bench.Bench.open(_bench(os.path.join(d, "b")))
        t = b.traits()
        assert t["order_marked"] == {"yes": 1, "no": 0, "not_said": 2}, t
        assert t["text_marked"] == {"yes": 0, "no": 1, "not_said": 2}, t
        assert bench.trait_state({}, "order_marked") == "not_said"
        assert bench.trait_state({"order_marked": False}, "order_marked") == "no"


def test_content_is_detected_from_the_truth():
    with tempfile.TemporaryDirectory() as d:
        b = bench.Bench.open(_bench(os.path.join(d, "b")))
        assert not b.has_content()
        c = bench.Bench.open(_bench(os.path.join(d, "c"), pages=[
            _page(0, blocks=[{"block_id": 0, "box": [0, 0, 1, 1], "label": "text",
                              "score": None, "order": 0, "content": "abc", "kind": "text"}])]))
        assert c.has_content()


def test_a_different_experiment_may_not_be_written_under_an_existing_label():
    """The sentence was in two documents and in no code.

    `core/book.py` and `CLAUDE.md` both said a command about to write a
    different identity under an existing label refuses and asks for `--run`.
    `identity` was computed, written, and read back by NOTHING: two runs of
    one model at two thresholds landed in one directory, the second over the
    first, under its name and beside its snapshot.

    Four cases, because three of them are ways of being wrong:
      the same experiment again        -- allowed, that is a resume
      a different identity             -- refused, and it names both
      a run that records no identity   -- refused: "I cannot tell" is not
                                          "the same"
      a page selector over a whole run -- refused, because the identity is
                                          over the model and the knobs and
                                          cannot see one
    """
    from booksmith.core import book as book_mod
    from booksmith.core.errors import Refusal
    with tempfile.TemporaryDirectory() as d:
        run = os.path.join(d, "detect", "M")
        os.makedirs(run)
        with open(os.path.join(run, "run.json"), "w", encoding="utf-8") as f:
            json.dump({"identity": "a" * 64}, f)

        book_mod.guard_identity(run, "a" * 64)          # the same: allowed

        for ident, spec, tell in (("b" * 64, "", "DIFFERENT experiment"),
                                  ("a" * 64, "1,2", "--pages")):
            try:
                book_mod.guard_identity(run, ident, spec)
            except Refusal as e:
                assert tell in str(e), (tell, str(e))
                assert "--run" in str(e), "the refusal names no way out"
            else:
                raise AssertionError(f"{tell}: passed in silence")

        with open(os.path.join(run, "run.json"), "w", encoding="utf-8") as f:
            json.dump({"when": "then"}, f)
        try:
            book_mod.guard_identity(run, "a" * 64)
        except Refusal as e:
            assert "no identity" in str(e), e
        else:
            raise AssertionError("a run with no identity was taken as equal")

        # And nothing there at all is not a conflict.
        book_mod.guard_identity(os.path.join(d, "detect", "N"), "a" * 64)
