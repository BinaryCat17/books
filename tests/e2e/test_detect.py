"""`books detect` end to end: a page really goes through, twice the same.

Both checks run the command as a subprocess and are the only ones that walk the
whole detect path -- every other check builds its detection fixture by hand.

The bench comes from the fixture, drawn here; the weights cannot be drawn, so
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
    """The whole path through the command line, weights and all: every other
    check builds its detection fixture by hand and the locks read a detect
    directory rather than producing one."""
    _weights()
    out = os.path.join(tempfile.mkdtemp(), "d")
    r = _detect(slovar.pdf, out)
    assert r.returncode == 0, (
        f"books detect exited {r.returncode}:\n{r.stdout[-1500:]}\n"
        f"{r.stderr[-1500:]}")
    snap = json.load(open(os.path.join(out, "run.json"), encoding="utf-8"))
    for key in ("identity", "label", "source", "fingerprint", "knobs"):
        assert snap.get(key), f"the snapshot has no {key}"
    # The module the snapshot names is on disk.
    mod = os.path.join(ROOT, "src",
                       snap["adapter"]["module"].replace(".", "/") + ".py")
    assert os.path.isfile(mod), (
        f"the snapshot names adapter module {snap['adapter']['module']}, and "
        f"{mod} is not there: `replay --check` resolves the writer by that "
        f"name")
    pages = os.listdir(os.path.join(out, "pages"))
    assert len(pages) == 1, f"one page asked for, {len(pages)} written"


def test_detection_is_byte_reproducible_into_another_directory(slovar):
    """The same model on the same page, twice, into two directories: a sweep's
    numbers compare only if each run repeats byte for byte, and no page may
    carry a path that changes between runs. `--out` is pinned here too."""
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
