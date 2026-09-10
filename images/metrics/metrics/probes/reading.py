from metrics import reading as m
from metrics.base import Probe


def _edit(pages, fn):
    return {i: {**p, "blocks": [fn(dict(b)) for b in p.get("blocks") or []]} for i, p in pages.items()}


def probes(bench, run) -> list:
    pages = run.pages()
    base = m.measure(pages)
    charts = base["charts_answered"]
    answered = base["answered"]

    def M(fn):
        return m.measure(_edit(pages, fn))

    def prose(b):
        if (b.get("label") or "") == "chart" and (b.get("content") or ""):
            b["content"] = "a curve rising from left to right"
        return b

    def data(b):
        if (b.get("content") or "").strip():
            b["content"] = "a | b\n1 | 2\n3 | 4"
        return b

    return [
        Probe(n, w, f)
        for n, w, f in (
            (
                "every chart answered in prose",
                "none is a table of numbers",
                lambda: None if not charts else M(prose)["charts_as_data"] == 0,
            ),
            (
                "every answer made a numeric table",
                "every ANSWERED chart is one, and nothing else is counted",
                lambda: None if not charts else (lambda r: r["charts_as_data"] == charts)(M(data)),
            ),
            (
                "every block relabelled a chart",
                "the count follows the LABEL, so it rises",
                lambda: (
                    None
                    if not answered
                    else M(lambda b: {**b, "label": "chart"})["charts_as_data"] >= base["charts_as_data"]
                ),
            ),
            (
                "every answer replaced by one token repeated",
                "the loop share reaches its ceiling",
                lambda: (
                    None
                    if not answered
                    else (lambda r: r["looping"] == r["answered"] and r["loop_worst"] > 0.9)(
                        M(
                            lambda b: {
                                **b,
                                "content": "abc " * 200
                                if (b.get("content") or "").strip()
                                else b.get("content"),
                            }
                        )
                    )
                ),
            ),
            (
                "every answer made of OTSL merge cells",
                "markup that repeats is not the model repeating itself",
                lambda: (
                    None
                    if not answered
                    else M(
                        lambda b: {
                            **b,
                            "content": "<lcel>" * 60
                            if (b.get("content") or "").strip()
                            else b.get("content"),
                        }
                    )["looping"]
                    == 0
                ),
            ),
            (
                "every answer emptied",
                "nothing is answered and nothing is counted",
                lambda: (lambda r: r["answered"] == 0 and r["charts_as_data"] == 0 and (r["looping"] == 0))(
                    M(lambda b: {**b, "content": None})
                ),
            ),
        )
    ]
