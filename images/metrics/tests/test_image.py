import os
import re

import metrics

IMAGE = os.path.dirname(os.path.dirname(os.path.abspath(metrics.__file__)))
ROOT = os.path.dirname(os.path.dirname(IMAGE))


def test_every_path_the_readme_cites_exists():
    with open(os.path.join(IMAGE, "README.md"), encoding="utf-8") as f:
        cited = re.findall(r"`([^`\s]+/[^`\s]+)`", f.read())
    missing = [c for c in cited if "<" not in c and "{" not in c and not c.startswith(("/", "http", "~"))
               and not os.path.exists(os.path.join(IMAGE, c)) and not os.path.exists(os.path.join(ROOT, c))]
    assert not missing, missing
