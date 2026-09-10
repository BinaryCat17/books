"""Text normalisation before comparison: the boundary level, the latex level,
and what each one refuses to strip. Shared by the reading metric (`datasets`)
and the book builder (`processing`), which hides repeated blocks by the same
rule.

The level is a value that travels into every result (`norm_note`), or two
measurements from different days are incomparable in silence.
"""
import re
import unicodedata

from booksmith.core.errors import TextError
# --------------------------------------------------------- normalisation

# The default level; every result carries it, so no two runs compare blindly.
NORM = "boundary"

_DASHES = "‐‑‒–—―−­-"
_TAIL = ".,;:!?…"
_WS = re.compile(r"\s+")
_DEC = re.compile(r"(?<=\d),(?=\d)")

NORM_STEPS = {
    "none": [],
    "boundary": ["NFKC and spaces", "case", "dash/hyphen/minus",
                 "decimal comma", "trailing punctuation"],
    # Display maths arrives as `\[...\]` and the same fragment inside a
    # paragraph as `$...$`, so at "boundary" the two never match.
    "latex": ["math wrapper", "typeface commands", "indices inlined",
              "^{\\circ} -> °", "then the boundary steps"],
}
# Printed beside the number, so a CER cannot be read without what it ignores.
NORM_REFUSED = ("leading punctuation (removes 139, harms 4: '.850' == "
                "'850'), all punctuation (504 at harm 108: '6—2' == '6,2'), "
                "Cyrillic/Latin lookalikes (lift 2.70 against 3.06 "
                "without it)")


# Typeface changes shape, not meaning: named one by one, and stripped without a
# trace, since a space in place of `\mathrm{C}` halves the matches (414 of 1935
# against 841).
_TYPEFACE = ("mathrm", "mathbf", "mathit", "mathsf", "mathtt", "text",
               "textrm", "textbf", "textit", "boldsymbol", "operatorname",
               "left", "right", "displaystyle", "limits",
               "bf", "rm", "it", "mbox", "hbox")
# Commands that are a space in typesetting; stripping them would glue words.
_SPACE = ("quad", "qquad")
_WRAPPER = re.compile(r"^\s*(?:\\\[|\\\(|\$\$|\$)|(?:\\\]|\\\)|\$\$|\$)\s*$")
_HEAD = re.compile(r"\\(" + "|".join(_TYPEFACE) + r")(?![a-zA-Z])")
_SP = re.compile(r"\\(" + "|".join(_SPACE) + r")(?![a-zA-Z])")
_INDEX = re.compile(r"[_^]\{([^{}]*)\}")


def bare_math(s: str) -> str:
    """Strip wrapper and typeface off a LaTeX fragment, keeping command names.

    Its own function, not a line inside `normalize`.
    """
    if not s:
        return ""
    s = s.strip()
    # Twice: `\[` on the left and `\]` on the right are two different ends.
    for _ in range(2):
        s = _WRAPPER.sub("", s).strip()
    s = (s.replace("^{\\circ}", "°").replace("^\\circ", "°")
         .replace("\\circ", "°"))
    s = _SP.sub(" ", s)
    s = _HEAD.sub("", s)
    s = _INDEX.sub(r"\1", s)
    s = re.sub(r"[_^]", "", s)
    s = (s.replace("\\%", "%").replace("\\cdot", "·")
         .replace("\\times", "x"))
    # The name of a meaningful command survives: `\alpha` -> `alpha`.
    s = re.sub(r"\\([a-zA-Z]+)", r"\1", s)
    return re.sub(r"[{}\\]", "", s)


def normalize(s: str, level: str = NORM) -> str:
    """Bring a string to a form where two spellings of one thing count equal.

    Exactly the steps measured at harm 0, and not one beyond them.
    """
    if level not in NORM_STEPS:
        raise TextError(f"normalisation level {level!r} is not declared; "
                        f"there are {sorted(NORM_STEPS)}")
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


# Rejections are per level; `NORM_REFUSED` holds those of the cell measurement.
REFUSED = {
    "boundary": NORM_REFUSED,
    "latex": ("strip spaces entirely (signal 1268 against 841, but false "
              "among the hidden 12.8% against 11.7%; refused not on profit "
              "but on the asymmetric cost of error: a false hide takes text "
              "away)"),
}


def norm_note(level: str = NORM) -> dict:
    return {"level": level, "steps": NORM_STEPS[level],
            "not_stripped": REFUSED.get(level, NORM_REFUSED)}
