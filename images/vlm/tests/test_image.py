import os
import re

import vlm

IMAGE = os.path.dirname(os.path.dirname(os.path.abspath(vlm.__file__)))
ROOT = os.path.dirname(os.path.dirname(IMAGE))


def test_every_path_the_readme_cites_exists():
    with open(os.path.join(IMAGE, "README.md"), encoding="utf-8") as f:
        cited = re.findall(r"`([^`\s]+/[^`\s]+)`", f.read())
    missing = [c for c in cited if "<" not in c and "{" not in c and not c.startswith(("/", "http", "~"))
               and not os.path.exists(os.path.join(IMAGE, c)) and not os.path.exists(os.path.join(ROOT, c))]
    assert not missing, missing


def test_every_knob_read_reaches_the_describe():
    from vlm import knobs, serve

    read = set()
    for dp, _, fs in os.walk(os.path.join(IMAGE, "vlm")):
        for f in (f for f in fs if f.endswith(".py")):
            with open(os.path.join(dp, f), encoding="utf-8") as fh:
                read |= set(re.findall(r'knobs\.(?:knob|number)\("([A-Z_0-9]+)"', fh.read()))
    missing = sorted(read - set(serve.DESCRIBED) - set(serve.NOT_DESCRIBED))
    assert not missing, (
        f"{missing} decide a run and never reach the describe, so never its identity. "
        f"Name them in serve.DESCRIBED, or in serve.NOT_DESCRIBED with the reason beside it."
    )
    assert set(serve.DESCRIBED) <= set(knobs.names())
