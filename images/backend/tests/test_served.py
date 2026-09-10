"""A model behind an endpoint: the describe is checked, a served run measures"""

import json
import os
import pytest
import support
from backend import store as book
from backend import job
from backend import page as page_mod
from backend import classes as policy
from backend import protocol as served
from backend import identity as stamp
from backend.errors import Refusal
from backend import layout as detect
from fake_layout import FakeLayout


def _raster(bench, tmp_path):
    from backend import raster

    png = str(tmp_path / "p0.png")
    with raster.open_pdf(bench.pdf) as doc:
        raster.render(doc[0], 144).save(png)
    return png


def _served(url, **more):
    return job.Job(settings={"LAYOUT_ENDPOINT": url, **more})


def test_a_describe_round_trips_and_a_wrong_one_is_refused_by_field():
    d = served.Describe(
        kind="layout",
        label="M",
        fingerprint={"sha256_weights": "ab"},
        classes={"text": "text"},
        reading_order="own",
        knobs={"A": "1"},
    )
    assert served.Describe.from_json(d.to_json()) == d
    assert d.labels == ("text",) and d.policy().role("text") == "text"
    good = d.to_json()
    v2 = policy.VOCABULARIES["PP-DocLayoutV2"]
    named = served.Describe.from_json({**good, "vocabulary": "PP-DocLayoutV2", "classes": dict(v2)})
    assert named.policy() == policy.POLICIES["PP-DocLayoutV2"]
    for field, value in (
        ("protocol", 2),
        ("kind", "oracle"),
        ("label", ""),
        ("fingerprint", {}),
        ("classes", {}),
        ("classes", {"text": "hologram"}),
        ("reading_order", "maybe"),
        ("knobs", {"A": 1}),
    ):
        bad = {**good, field: value}
        with pytest.raises(Refusal) as e:
            served.Describe.from_json(bad)
        assert field in str(e.value) or "protocol" in str(e.value), field
    with pytest.raises(Refusal) as e:
        served.Describe.from_json(
            {**good, "vocabulary": "PP-DocLayoutV2", "classes": {"text": "caption"}}
        )
    assert "maps it otherwise" in str(e.value), "a tree's name over another mapping"
    own = served.Describe.from_json({**good, "classes": {"text": "caption"}})
    assert own.vocabulary == "" and own.policy().cls("text") == "caption"
    with pytest.raises(Refusal):
        served.Describe.from_json({**good, "kind": "reader"})
    with pytest.raises(Refusal):
        served.Describe.from_json({**good, "kind": "hybrid"})
    assert served.root_of("http://h:1/v1/") == "http://h:1"
    assert served.root_of("http://h:1") == "http://h:1"


def test_identity_is_the_fingerprint_with_the_knobs_of_both_sides():
    d = served.Describe(
        kind="layout",
        label="M",
        fingerprint={"sha256_weights": "ab"},
        classes={"text": "text"},
        knobs={"LAYOUT_SCORE_THRESHOLD": "0.5"},
    )
    both = served.identity_of(d, {"PAGE_DPI": "144", "LAYOUT_ENDPOINT": "http://a"})
    assert both == stamp.identity(
        {"sha256_weights": "ab", "classes": {"text": "text"}},
        {"LAYOUT_SCORE_THRESHOLD": "0.5", "PAGE_DPI": "144"},
    )
    assert both == served.identity_of(
        d, {"PAGE_DPI": "144", "LAYOUT_ENDPOINT": "http://b"}
    ), "the address or the adapter moved the identity"
    assert both != served.identity_of(d, {"PAGE_DPI": "72"})
    with pytest.raises(Refusal):
        served.identity_of(d, {"LAYOUT_SCORE_THRESHOLD": "0.6"})
    own = served.Describe(
        kind="layout", label="M", fingerprint={"sha256_weights": "ab"}, classes={"Grid": "table"}
    )
    other = served.Describe(
        kind="layout", label="M", fingerprint={"sha256_weights": "ab"}, classes={"Grid": "text"}
    )
    assert served.identity_of(own, {}) != served.identity_of(other, {})
    named = served.Describe(
        kind="layout",
        label="M",
        fingerprint={"sha256_weights": "ab"},
        classes=dict(policy.VOCABULARIES["DocLayNet"]),
        vocabulary="DocLayNet",
    )
    assert served.fingerprint_of(named) == {"sha256_weights": "ab"}


def test_the_adapter_refuses_what_the_model_did_not_declare(bench, tmp_path):
    png = _raster(bench, tmp_path)
    with FakeLayout(bench.truth_dir, keep_content=True) as fake:
        with _served(fake.url).active():
            det = detect._adapter()
            assert det.label() == "truth" and det.where() == fake.url
            assert det.served()["kind"] == "layout"
            with pytest.raises(Refusal) as e:
                det.read(png, 0, 144.0)
            assert "content" in str(e.value)
    with _served("http://127.0.0.1:1").active(), pytest.raises(Refusal) as e:
        detect._adapter()
    assert "describe" in str(e.value)
    with _served("").active(), pytest.raises(Refusal):
        detect._adapter()


def test_the_adapter_refuses_a_page_that_is_not_the_sheet_it_sent(bench, tmp_path):
    b = bench
    png = _raster(b, tmp_path)
    assert served.png_size(png) is not None
    cases = {
        "dpi": (lambda d: {**d, "dpi": 72.0}, "layout"),
        "sheet": (lambda d: {**d, "width": d["width"] // 2}, "layout"),
        "declare": (lambda d: {**d, "blocks": [{**d["blocks"][0], "label": "martian"}]}, "layout"),
        "kind": (lambda d: {**d, "blocks": [{**d["blocks"][0], "kind": "none"}]}, "hybrid"),
    }
    for word, (edit, kind) in cases.items():
        with FakeLayout(b.truth_dir, kind=kind, answer=edit) as fake:
            with _served(fake.url).active():
                det = detect._adapter()
                with pytest.raises(Refusal) as e:
                    det.read(png, 0, 144.0)
                assert word in str(e.value), (word, str(e.value))
    with FakeLayout(b.truth_dir) as fake, _served(fake.url).active():
        page = detect._adapter().read(png, 0, 144.0)
        assert page.width and page.dpi == 144.0


def test_a_layout_key_rides_as_a_secret_and_reaches_the_endpoint(bench, tmp_path):
    png = _raster(bench, tmp_path)
    with FakeLayout(bench.truth_dir) as fake:
        j = job.Job(
            settings={"LAYOUT_ENDPOINT": fake.url},
            secrets={"LAYOUT_API_KEY": "sk-layout"},
        )
        with j.active():
            det = detect._adapter()
            assert det.read(png, 0, 144.0).index == 0
        assert fake.seen[-1]["authorization"] == "Bearer sk-layout"
        assert "sk-layout" not in json.dumps(det.served())


def test_level_two_reads_through_a_hybrid_only_when_it_serves_the_chat_route(bench):
    from backend import transport as openai_http

    with FakeLayout(bench.truth_dir, kind="hybrid") as fake:
        with job.Job(settings={"VLM_ENDPOINT": fake.url + "/v1"}).active():
            with pytest.raises(Refusal) as e:
                openai_http.Http().check()
            assert "chat route" in str(e.value)
    with FakeLayout(bench.truth_dir, kind="hybrid", openai={"model": "M"}) as fake:
        with job.Job(settings={"VLM_ENDPOINT": fake.url + "/v1", "MODEL_NAME": "M"}).active():
            who = openai_http.Http().check()
            assert who["matched"] and who["describe"]["label"] == "truth"
        with job.Job(settings={"VLM_ENDPOINT": fake.url + "/v1", "MODEL_NAME": "N"}).active():
            with pytest.raises(Refusal):
                openai_http.Http().check()
    with FakeLayout(bench.truth_dir) as fake:
        with job.Job(settings={"VLM_ENDPOINT": fake.url + "/v1"}).active():
            with pytest.raises(Refusal) as e:
                openai_http.Http().check()
            assert "layout model" in str(e.value)


def test_a_hybrid_files_as_a_read_run_with_its_own_boxes(bench, tmp_path):
    out = str(tmp_path / "read" / "truth")
    with FakeLayout(bench.truth_dir, kind="hybrid") as fake, support.said():
        with _served(fake.url).active():
            detect.run(bench.pdf, out, det=detect._adapter(), hybrid=True)
        snap = book.snapshot_beside(os.path.join(out, "pages"))
        assert snap["layout"] == "own" and snap["detection"] is None and snap["kinds"] == ["text"]
        pages = page_mod.load_pages(os.path.join(out, "pages"))
        assert any(bl.get("content") for p in pages.values() for bl in p["blocks"])
    with FakeLayout(bench.truth_dir) as fake, support.said():
        with _served(fake.url).active(), pytest.raises(Refusal) as e:
            detect.run(bench.pdf, out + "2", det=detect._adapter(), hybrid=True)
        assert "hybrid" in str(e.value)
