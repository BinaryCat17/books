"""One loader, one identity check, three trait states -- and each can fail"""

import json
import os
import shutil
import tempfile
from metrics.errors import Unmeasurable
from metrics import page
from metrics import identity as stamp
from metrics import settings as config
from metrics import bench


def _page(i, blocks=(), meta=None):
    return {
        "index": i,
        "width": 100,
        "height": 100,
        "dpi": 72.0,
        "blocks": list(blocks),
        "raw": None,
        "meta": meta or {},
    }


LABEL = "PP-DocLayoutV2"


def _book(d, man=None, sha="cd" * 32, name="book"):
    root = os.path.join(d, "processed", name)
    os.makedirs(root, exist_ok=True)
    if man is None:
        man = {"source": {"name": "book.pdf", "sha256": sha}}
    with open(os.path.join(root, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(man, f)
    return root


def _bench(root, sha="ab" * 32, pages=None, run_sha=None, label=LABEL):
    os.makedirs(os.path.join(root, "truth"))
    for i, p in enumerate(
        pages
        or [_page(0), _page(1, meta={"order_marked": True}), _page(2, meta={"text_marked": False})]
    ):
        with open(os.path.join(root, "truth", f"{i:04d}.json"), "w") as f:
            json.dump(p, f)
    with open(os.path.join(root, "manifest.json"), "w") as f:
        json.dump({"book": os.path.basename(root), "source": {"name": "x.pdf", "sha256": sha}}, f)
    run = os.path.join(root, "detect", label)
    os.makedirs(os.path.join(run, "pages"))
    for i in range(3):
        with open(os.path.join(run, "pages", f"{i:04d}.json"), "w") as f:
            json.dump(_page(i), f)
    with open(os.path.join(run, "run.json"), "w") as f:
        json.dump(
            {
                "source": {"path": "x.pdf", "sha256": run_sha or sha},
                "policy": {"vocabulary": "PP-DocLayoutV2"},
            },
            f,
        )
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


def test_a_book_without_truth_opens_by_its_own_door_and_not_by_open():
    with tempfile.TemporaryDirectory() as d:
        root = _book(d)
        b = bench.Bench.no_truth(root)
        assert b.name == "book" and b.truth_dir == ""
        assert b.sha256 == "cd" * 32
        assert b.pdf is None
        try:
            bench.Bench.open(root)
        except Unmeasurable as e:
            assert "truth/" in str(e)
        else:
            raise AssertionError("a book without truth opened as a bench")


def test_a_book_without_a_manifest_is_not_a_book():
    with tempfile.TemporaryDirectory() as d:
        try:
            bench.Bench.no_truth(d)
        except Unmeasurable as e:
            assert "is not a book: expected manifest.json" in str(e), e
        else:
            raise AssertionError("a directory with no manifest opened as a book")


def test_a_book_whose_manifest_names_no_sha_is_not_a_book():
    with tempfile.TemporaryDirectory() as d:
        for man in ({"about": "a book"}, {"source": {}}, {"source": {"name": "book.pdf"}}):
            root = _book(d, man, name=f"b{len(str(man))}")
            try:
                bench.Bench.no_truth(root)
            except Unmeasurable as e:
                assert "sha256" in str(e)
            else:
                raise AssertionError(f"{man} opened as a book with identity")


def test_the_books_that_declare_themselves_truthless_open():
    for n in ("real-tables20", "real-holdout20", "real-test25"):
        b = bench.Bench.no_truth(os.path.join(config.ROOT, "bench", n))
        assert b.truth_dir == "" and b.sha256
        assert b.pdf and os.path.isfile(b.pdf), n


def test_a_manifest_may_name_a_file_and_not_a_path():
    with tempfile.TemporaryDirectory() as d:
        for bad in ("/etc/hosts", "../../../../etc/passwd", "..", "a/b.pdf"):
            root = _book(d, {"source": {"name": bad, "sha256": "ab" * 32}})
            try:
                bench.Bench.no_truth(root)
            except Unmeasurable as e:
                assert "is a path and not a file name" in str(e), e
            else:
                raise AssertionError(f"{bad!r} was accepted as a source name")


def test_the_scan_beside_the_book_is_checked_by_sha_too():
    with tempfile.TemporaryDirectory() as d:
        root = _book(d)
        with open(os.path.join(root, "book.pdf"), "wb") as f:
            f.write(b"not a pdf at all")
        try:
            bench.Bench.no_truth(root)
        except Unmeasurable as e:
            assert "is not the scan" in str(e), e
        else:
            raise AssertionError("a foreign scan beside the book was accepted")


def test_a_truthless_book_answers_for_its_scan_from_the_checked_lookup_only():
    with tempfile.TemporaryDirectory() as d:
        root = _book(d, {"source": {"sha256": "cd" * 32}})
        with open(os.path.join(root, "book.pdf"), "wb") as f:
            f.write(b"whatever bytes")
        b = bench.Bench.no_truth(root)
        assert b.scan == ""
        assert b.pdf is None, b.pdf


def test_a_bench_whose_truth_went_missing_is_not_a_truthless_book():
    with tempfile.TemporaryDirectory() as d:
        for half in ("truth.previous", "truth.new"):
            root = _book(d, name=f"b-{half}")
            os.makedirs(os.path.join(root, half))
            try:
                bench.Bench.no_truth(root)
            except Unmeasurable as e:
                assert half in str(e), e
            else:
                raise AssertionError(f"a build interrupted at {half} opened")


def test_the_scan_of_a_built_book_is_found_in_raw_and_checked_by_sha():
    with tempfile.TemporaryDirectory() as d:
        raw = os.path.join(d, "raw")
        os.makedirs(raw)
        with open(os.path.join(raw, "book.pdf"), "wb") as f:
            f.write(b"a scan, for the purposes of a hash")
        real = stamp.sha256(os.path.join(raw, "book.pdf"))
        found = bench.Bench.no_truth(_book(d, sha=real, name="right"))
        assert found.pdf == os.path.join(raw, "book.pdf")
        assert found.scan == found.pdf
        near = real[:12] + ("0" if real[12] != "0" else "1") + real[13:]
        try:
            bench.Bench.no_truth(_book(d, sha=near, name="wrong"))
        except Unmeasurable as e:
            assert "is not the scan" in str(e) and real[:12] in str(e)
        else:
            raise AssertionError("a foreign scan in raw/ was accepted")


def test_a_run_knows_which_level_it_is_of():
    with tempfile.TemporaryDirectory() as d:
        root = _bench(os.path.join(d, "b"))
        assert bench.Run.open(os.path.join(root, "detect", LABEL)).kind == "detect"
        assert bench.Run.bare(os.path.join(root, "detect", LABEL, "pages")).kind == ""
        stray = os.path.join(d, "scratch", LABEL)
        os.makedirs(stray)
        shutil.copytree(os.path.join(root, "detect", LABEL, "pages"), os.path.join(stray, "pages"))
        shutil.copy(os.path.join(root, "detect", LABEL, "run.json"), stray)
        assert bench.Run.open(stray).kind == "", bench.Run.open(stray).kind


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
        assert bench.same_book(b, b.run()).startswith("sha256 not checked: the field is absent")


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
        c = bench.Bench.open(
            _bench(
                os.path.join(d, "c"),
                pages=[
                    _page(
                        0,
                        blocks=[
                            {
                                "block_id": 0,
                                "box": [0, 0, 1, 1],
                                "label": "text",
                                "score": None,
                                "order": 0,
                                "content": "abc",
                                "kind": "text",
                            }
                        ],
                    )
                ],
            )
        )
        assert c.has_content()


def test_a_different_experiment_may_not_be_written_under_an_existing_label():
    from metrics import store as book_mod
    from metrics.errors import Refusal

    with tempfile.TemporaryDirectory() as d:
        run = os.path.join(d, "detect", "M")
        os.makedirs(run)
        with open(os.path.join(run, "run.json"), "w", encoding="utf-8") as f:
            json.dump({"identity": "a" * 64}, f)
        book_mod.guard_identity(run, "a" * 64)
        for ident, spec, tell in (
            ("b" * 64, "", "DIFFERENT experiment"),
            ("a" * 64, "1,2", "--pages"),
        ):
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
        book_mod.guard_identity(os.path.join(d, "detect", "N"), "a" * 64)
