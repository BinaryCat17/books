from collections.abc import Sequence

WORDS = {"ours": "ours_top_down_left_right"}
MODEL_RANK = "model_rank"


def declare(source: str, rule: str = "") -> str | None:
    if source == "model":
        return MODEL_RANK
    if source == "none":
        return None
    if source == "ours":
        if not (isinstance(rule, str) and rule.strip().lower().startswith("ours")):
            raise ValueError(
                f"an order of ours must be declared by a rule word starting with `ours`, not {rule!r}"
            )
        return rule
    raise ValueError(f"reading order source {source!r}: model, ours or none")


def permutation(
    labels: Sequence[str],
    boxes: Sequence,
    width: float,
    height: float,
    index: int,
    pol: object,
    which: str | None = None,
) -> list[int]:
    return sorted(range(len(boxes)), key=lambda i: (boxes[i][1], boxes[i][0]))
