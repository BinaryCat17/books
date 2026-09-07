"""Every path a module computes from its own `__file__` points where it claims.

A count of `dirname`s breaks at the first move of the file, silently: the
package move of 2026-09-07 took `config.py` one level deeper, and had the
count stayed, `.env` would have been looked for under `src/` and every secret
would have read as unset. `schema.py` would have globbed nothing and counted
zero everywhere. So each such constant is asserted against a landmark that
only the right directory holds.
"""
import os

import support
from booksmith.core import config, replay, schema
from booksmith.core import knobs
from booksmith.datasets import accept as acceptance
from booksmith.processing.read.rented import paddleocr_vl
from booksmith.remote import ledger


def _is_repo_root(p):
    return os.path.isfile(os.path.join(p, "pyproject.toml")) and \
        os.path.isdir(os.path.join(p, "src", "booksmith"))


def _is_package(p):
    return os.path.isfile(os.path.join(p, "__init__.py")) and \
        os.path.isdir(os.path.join(p, "core"))


def test_config_root_is_the_repository():
    assert _is_repo_root(config.ROOT), config.ROOT
    assert config.ENV_FILE == os.path.join(config.ROOT, ".env")


def test_schema_root_is_the_repository():
    assert _is_repo_root(schema.ROOT), schema.ROOT


def test_acceptance_root_is_the_repository():
    assert _is_repo_root(acceptance.ROOT), acceptance.ROOT


def test_knobs_src_is_the_package():
    assert _is_package(knobs.SRC), knobs.SRC


def test_replay_pkg_is_the_package():
    assert _is_package(replay.PKG), replay.PKG


def test_the_rented_job_ships_the_whole_package():
    """`spec()` copies `PKG` to the box; two `dirname`s from a file that
    moves is a partial package shipped in silence, learnt on a rented card."""
    assert _is_package(paddleocr_vl.PKG), paddleocr_vl.PKG


def test_ledger_root_is_the_repository():
    assert _is_repo_root(ledger._ROOT), ledger._ROOT


def test_the_detect_command_can_actually_run():
    """`books detect` was BROKEN for a day and the suite was green.

    The package move left `sha256_command` assembled from `here` plus a
    literal `processing/layout/detect.py`, which was right while `here` was
    `src/booksmith` and became `.../processing/layout/processing/layout/
    detect.py` the moment the module moved. Every real run raised
    FileNotFoundError; nothing noticed, because every check builds its
    detection fixture BY HAND and the acceptance reports READ a detect
    directory rather than producing one.

    So this one produces one: two pages of the smallest bench, through the
    command line, into a temporary directory. It is the only check that walks
    the whole detect path, and it is here rather than in a bench file because
    what it guards is the root computations this file is about.
    """
    import json
    import subprocess
    import sys as _s
    import tempfile
    root = os.path.dirname(os.path.dirname(support.SRC))
    pdf = os.path.join(root, "bench", "slovar", "slovar.pdf")
    if not os.path.isfile(pdf):
        support.skip("no bench/slovar/slovar.pdf: build it with `books synth`")
    out = os.path.join(tempfile.mkdtemp(), "d")
    r = subprocess.run([_s.executable, "-m", "booksmith.cli", "detect", pdf,
                        "--out", out, "--pages", "1"],
                       cwd=root, capture_output=True, text=True,
                       env={**os.environ,
                            "PYTHONPATH": os.path.join(root, "src")})
    assert r.returncode == 0, (
        f"books detect exited {r.returncode}:\n{r.stdout[-1500:]}\n"
        f"{r.stderr[-1500:]}")
    snap = json.load(open(os.path.join(out, "run.json"), encoding="utf-8"))
    for key in ("identity", "label", "source", "fingerprint", "knobs"):
        assert snap.get(key), f"the snapshot has no {key}"
    # THE MODULE THE SNAPSHOT NAMES IS ON DISK. This line ended in `or True`
    # for a day -- a check that cannot fail, in the branch that added "a skip
    # is not a pass", reading to the mutation battery as coverage. The path is
    # under `src/`, which is what the `or True` was papering over.
    mod = os.path.join(os.path.dirname(support.SRC),
                       snap["adapter"]["module"].replace(".", "/") + ".py")
    assert os.path.isfile(mod), (
        f"the snapshot names adapter module {snap['adapter']['module']}, and "
        f"{mod} is not there: `replay --check` resolves the writer by that "
        f"name")
    pages = os.listdir(os.path.join(out, "pages"))
    assert len(pages) == 1, f"one page asked for, {len(pages)} written"
    return out, root, pdf


def test_detection_is_byte_reproducible_into_another_directory():
    """The same model on the same page, twice, into two directories.

    A sweep lays six models beside each other and its numbers are only a
    comparison if each is reproducible. It was not: every page carried
    `meta["raster"]`, the absolute path of the scratch PNG it was rendered to
    -- a file deleted at the end of the run -- so two runs of ONE model
    differed on 13 of 13 pages and were identical without it. Nothing read the
    key. What is worth keeping about the render is the dpi and the size, and
    `Page` carries both.

    This also pins `--out` against the book directory: resolving the scan only
    when `--out` was absent handed the directory itself to the renderer.
    """
    import json
    import subprocess
    import sys as _s
    import tempfile
    root = os.path.dirname(os.path.dirname(support.SRC))
    pdf = os.path.join(root, "bench", "slovar", "slovar.pdf")
    if not os.path.isfile(pdf):
        support.skip("no bench/slovar/slovar.pdf: build it with `books synth`")
    outs = []
    for _ in range(2):
        d = os.path.join(tempfile.mkdtemp(), "d")
        r = subprocess.run([_s.executable, "-m", "booksmith.cli", "detect",
                            os.path.join(root, "bench", "slovar"),
                            "--out", d, "--pages", "1"],
                           cwd=root, capture_output=True, text=True,
                           env={**os.environ,
                                "PYTHONPATH": os.path.join(root, "src")})
        assert r.returncode == 0, (
            f"books detect on a book directory with --out exited "
            f"{r.returncode}:\n{r.stdout[-800:]}{r.stderr[-800:]}")
        outs.append(d)
    a, b = (open(os.path.join(d, "pages", "0000.json"), "rb").read()
            for d in outs)
    assert a == b, "two runs of one model into two directories differ"
    ia, ib = (json.load(open(os.path.join(d, "run.json"),
                             encoding="utf-8"))["identity"] for d in outs)
    assert ia == ib, f"the same experiment got two identities: {ia} {ib}"
