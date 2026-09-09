"""`books detect` end to end: a page really goes through, twice the same.

Both checks run the command as a subprocess, and they are the only ones that
walk the whole detect path -- every other check builds its detection fixture by
hand. The day the path from a module to its own source file broke, every real
run raised FileNotFoundError and the suite stayed green.

The bench comes from the fixture, drawn here; the WEIGHTS cannot be drawn, so
their absence is a skip with a reason.
"""
import json
import os
import subprocess
import sys
import tempfile

import pytest

from booksmith.core.config import ROOT
from booksmith.processing.layout.adapters import doclayout


def _weights():
    d = doclayout.weights_dir()
    if not os.path.exists(os.path.join(d, "inference.onnx")):
        pytest.skip(f"no detection weights in {d}: `books doctor` says how")
    try:
        import onnxruntime                                     # noqa: F401
    except ImportError:
        pytest.skip('no onnxruntime: pip install -e ".[detect]"')


def _detect(what, out):
    return subprocess.run(
        [sys.executable, "-m", "booksmith.cli", "detect", what,
         "--out", out, "--pages", "1"],
        cwd=ROOT, capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": os.path.join(ROOT, "src")})


def test_the_detect_command_can_actually_run(slovar):
    """`books detect` was BROKEN for a day and the suite was green.

    The package move left the command's own source path assembled from a base
    plus a literal, right while the base was `src/booksmith` and doubled the
    moment the module moved a directory down. Every real run raised
    FileNotFoundError; nothing noticed, because every check builds its detection
    fixture BY HAND and the locks READ a detect directory rather than producing
    one. So this one produces one, through the command line.
    """
    _weights()
    out = os.path.join(tempfile.mkdtemp(), "d")
    r = _detect(slovar.pdf, out)
    assert r.returncode == 0, (
        f"books detect exited {r.returncode}:\n{r.stdout[-1500:]}\n"
        f"{r.stderr[-1500:]}")
    snap = json.load(open(os.path.join(out, "run.json"), encoding="utf-8"))
    for key in ("identity", "label", "source", "fingerprint", "knobs"):
        assert snap.get(key), f"the snapshot has no {key}"
    # THE MODULE THE SNAPSHOT NAMES IS ON DISK. This line ended in `or True` for
    # a day -- a check that cannot fail, reading to the mutation battery as
    # coverage.
    mod = os.path.join(ROOT, "src",
                       snap["adapter"]["module"].replace(".", "/") + ".py")
    assert os.path.isfile(mod), (
        f"the snapshot names adapter module {snap['adapter']['module']}, and "
        f"{mod} is not there: `replay --check` resolves the writer by that "
        f"name")
    pages = os.listdir(os.path.join(out, "pages"))
    assert len(pages) == 1, f"one page asked for, {len(pages)} written"


def test_detection_is_byte_reproducible_into_another_directory(slovar):
    """The same model on the same page, twice, into two directories.

    A sweep lays six models beside each other and its numbers are only a
    comparison if each is reproducible. It was not: every page carried the
    absolute path of the scratch PNG it was rendered to -- a file deleted at the
    end of the run -- so two runs of ONE model differed on every page and were
    identical without it. Nothing read the key.

    This also pins `--out` against the book directory: resolving the scan only
    when `--out` was absent handed the directory itself to the renderer.
    """
    _weights()
    outs = []
    for _ in range(2):
        d = os.path.join(tempfile.mkdtemp(), "d")
        r = _detect(slovar.root, d)
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
