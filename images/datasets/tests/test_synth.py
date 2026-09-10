import json
import os

import jsonschema

from datasets import settings, synth
from datasets.page import load_pages
from support import said


def test_the_drawn_bench_is_pages_in_the_page_format(tmp_path):
    out = str(tmp_path / "slovar")
    with said():
        synth.build(out, None, 1, "old", book="slovar")
    with open(os.path.join(settings.schema_dir(), "page.schema.json"), encoding="utf-8") as f:
        schema = json.load(f)
    pages = load_pages(os.path.join(out, "truth"))
    assert len(pages) > 5 and os.path.isfile(os.path.join(out, "slovar.pdf"))
    for p in pages.values():
        jsonschema.validate(p, schema)
        assert p["meta"]["text_marked"] is True
    with open(os.path.join(out, "manifest.json"), encoding="utf-8") as f:
        assert json.load(f)["source"]["name"] == "slovar.pdf"
