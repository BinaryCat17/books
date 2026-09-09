"""The spread-cut gauge agrees with the veto in `djvu.py`.

An agreement between two files: the gauge draws its own fourteen sheets and
carries its own copy of the column choice, so drifting from `djvu.py` it keeps
printing numbers -- about something other than what the pipeline does. That is
how "a 0.5 % threshold catches 84 % of the controls" became unverifiable: the
script that measured it never entered the tree.
"""
import importlib.util
import io
import os
import sys
from contextlib import redirect_stdout

import pytest


def test_the_probe_selfcheck_agrees_with_the_veto():
    """`spread_probe.py --selfcheck` must agree with `djvu.py`."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "spread_probe.py")
    if not os.path.exists(path):
        pytest.skip(f"no {path} -- the gauge is not in the tree")
    spec = importlib.util.spec_from_file_location("spread_probe", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["spread_probe"] = mod
    spec.loader.exec_module(mod)
    assert len(mod.CASES) >= 14, (
        f"selfcheck sheets {len(mod.CASES)}, there were 14: cases have "
        f"been struck out, not added")
    buf = io.StringIO()
    with redirect_stdout(buf):
        bad = mod.selfcheck()
    # `selfcheck` returns 1 on ANY divergence, not their number: they are
    # named in what it printed, so take them from there -- otherwise a failure
    # says "1" and keeps quiet about which sheet diverged.
    assert bad == 0, (f"the gauge diverged from the veto, sheets "
                      f"{len(mod.CASES)}:\n" + buf.getvalue())
