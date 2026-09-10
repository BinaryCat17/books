import re
import unicodedata
from metrics.errors import TextError

NORM = "boundary"
_DASHES = "‐‑‒–—―−\xad-"
_TAIL = ".,;:!?…"
_WS = re.compile("\\s+")
_DEC = re.compile("(?<=\\d),(?=\\d)")
NORM_STEPS = {
    "none": [],
    "boundary": [
        "NFKC and spaces",
        "case",
        "dash/hyphen/minus",
        "decimal comma",
        "trailing punctuation",
    ],
    "latex": [
        "math wrapper",
        "typeface commands",
        "indices inlined",
        "^{\\circ} -> °",
        "then the boundary steps",
    ],
}
NORM_REFUSED = "leading punctuation (removes 139, harms 4: '.850' == '850'), all punctuation (504 at harm 108: '6—2' == '6,2'), Cyrillic/Latin lookalikes (lift 2.70 against 3.06 without it)"
_TYPEFACE = (
    "mathrm",
    "mathbf",
    "mathit",
    "mathsf",
    "mathtt",
    "text",
    "textrm",
    "textbf",
    "textit",
    "boldsymbol",
    "operatorname",
    "left",
    "right",
    "displaystyle",
    "limits",
    "bf",
    "rm",
    "it",
    "mbox",
    "hbox",
)
_SPACE = ("quad", "qquad")
_WRAPPER = re.compile("^\\s*(?:\\\\\\[|\\\\\\(|\\$\\$|\\$)|(?:\\\\\\]|\\\\\\)|\\$\\$|\\$)\\s*$")
_HEAD = re.compile("\\\\(" + "|".join(_TYPEFACE) + ")(?![a-zA-Z])")
_SP = re.compile("\\\\(" + "|".join(_SPACE) + ")(?![a-zA-Z])")
_INDEX = re.compile("[_^]\\{([^{}]*)\\}")


def bare_math(s: str) -> str:
    if not s:
        return ""
    s = s.strip()
    for _ in range(2):
        s = _WRAPPER.sub("", s).strip()
    s = s.replace("^{\\circ}", "°").replace("^\\circ", "°").replace("\\circ", "°")
    s = _SP.sub(" ", s)
    s = _HEAD.sub("", s)
    s = _INDEX.sub("\\1", s)
    s = re.sub("[_^]", "", s)
    s = s.replace("\\%", "%").replace("\\cdot", "·").replace("\\times", "x")
    s = re.sub("\\\\([a-zA-Z]+)", "\\1", s)
    return re.sub("[{}\\\\]", "", s)


def normalize(s: str, level: str = NORM) -> str:
    if level not in NORM_STEPS:
        raise TextError(f"normalisation level {level!r} is not declared; there are {sorted(NORM_STEPS)}")
    if s is None:
        return ""
    if level == "none":
        return s
    if level == "latex":
        s = bare_math(s)
    s = unicodedata.normalize("NFKC", s)
    s = _WS.sub(" ", s).strip()
    s = s.casefold()
    s = "".join("-" if c in _DASHES else c for c in s)
    s = _DEC.sub(".", s)
    return s.rstrip(_TAIL)


REFUSED = {
    "boundary": NORM_REFUSED,
    "latex": "strip spaces entirely (signal 1268 against 841, but false among the hidden 12.8% against 11.7%; refused not on profit but on the asymmetric cost of error: a false hide takes text away)",
}


def norm_note(level: str = NORM) -> dict:
    return {
        "level": level,
        "steps": NORM_STEPS[level],
        "not_stripped": REFUSED.get(level, NORM_REFUSED),
    }
