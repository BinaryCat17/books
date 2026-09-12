from __future__ import annotations
import re
from layout.errors import Refusal


LABEL_OK = re.compile("^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")
ASIDE = (".new", ".old")


def safe_label(name: str, what: str) -> str:
    name = (name or "").strip()
    if not LABEL_OK.match(name) or name.endswith(ASIDE):
        raise Refusal(
            f"{what}: {name!r} cannot be a run directory name. A label is the MODEL's name, letters, digits and . _ + - only. This one comes from the model itself (the weights' own name, the variant, the weights file), so a name like this means the weights do not declare one -- pass --run <name> and the run is filed under that."
        )
    return name

