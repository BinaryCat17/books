"""Text normalisation before comparison: the boundary, the latex step, and
what was refused. Shared by the reading metric (`datasets`) and the book
builder (`processing`), which hides repeated blocks by the same rule.

The level is a VALUE that travels into every result (`norm_note`), or two
measurements from different days are incomparable in silence.
"""
import re
import unicodedata

# --------------------------------------------------------- normalisation
#
# The level is a VALUE: it travels into the returned dict, or two measurements
# from different days are incomparable in silence.
NORM = "boundary"

_DASHES = "‐‑‒–—―−­-"
_TAIL = ".,;:!?…"
_WS = re.compile(r"\s+")
_DEC = re.compile(r"(?<=\d),(?=\d)")

NORM_STEPS = {
    "none": [],
    "boundary": ["NFKC and spaces", "case", "dash/hyphen/minus",
                 "decimal comma", "trailing punctuation"],
    # SIXTH STEP, MEASURED SEPARATELY. Everything above was measured on CELLS
    # (32 634 over six books) and says nothing about matching a formula against
    # prose: display maths arrives as `\[...\]`, the same fragment inside a
    # paragraph as `$...$` or plain characters (`1728°C`), and at "boundary"
    # they match 0 times by construction.
    #
    # "Технология огнеупоров", 1935 blocks nested by box inside a text block:
    # the text is found among blocks that REMAIN in the book for 841 (43.5 %)
    # at a worst background of 98 (5.1 %), ratio 8.6. Stripping typeface with a
    # SPACE gave 414 (21.4 %) at background 42 (2.2 %), ratio 9.9 -- better
    # ratio, near-equal share of false among the hidden (10.1 % against
    # 11.7 %), half the finds. Chosen by the second number: we hide blocks, so
    # the cost of error counts from what is hidden. (A block searched in prose
    # that contains it self-matches at 99.0 %; excluding it, 35.1 %.)
    #
    # REJECTED -- stripping spaces entirely on top of this: signal 1268
    # (65.5 %) against 841, background 162 (8.4 %) against 98, order holding on
    # all four shifts (6.5/5.7/2.9 against 5.1/4.6/2.4). Profitable too, net
    # 1106 against 743, +363 correct hides for +64 false, 5.7 to 1, and refused
    # because a false hide takes text out of the book while a missed repeat
    # only leaves a line.
    #
    # STRIPPED: wrapper, typeface commands, indices inlined, `^{\circ}` to a
    # degree sign; KEPT: command NAMES, `\alpha` -> `alpha`. Dropping all
    # commands gives 90 more matches and lifts the background 3.4 % -> 4.6 %,
    # signal to background 20.1 -> 15.9: noise. Rejected.
    "latex": ["math wrapper", "typeface commands", "indices inlined",
              "^{\\circ} -> °", "then the boundary steps"],
    # What was rejected is printed beside the number; see `NORM_REFUSED`.
}
# Printed beside the number. Otherwise "CER 0.03" will mean anything at all a
# month from now, and the first proposal will be to strip punctuation too.
NORM_REFUSED = ("leading punctuation (removes 139, harms 4: '.850' == "
                "'850'), all punctuation (504 at harm 108: '6—2' == '6,2'), "
                "Cyrillic/Latin lookalikes (lift 2.70 against 3.06 "
                "without it)")


# LaTeX typeface commands change the SHAPE, not the meaning, so they go; the
# lists are named one by one, since `\alpha` IS meaning. Typeface goes WITHOUT
# A TRACE, a spacing command becomes a space: a space for every typeface
# command made `\mathrm{C}` into " C" where prose has `1470—1728°C` tight,
# halving the matches, 414 against 841 over 1935 candidates.
_TYPEFACE = ("mathrm", "mathbf", "mathit", "mathsf", "mathtt", "text",
               "textrm", "textbf", "textit", "boldsymbol", "operatorname",
               "left", "right", "displaystyle", "limits",
               "bf", "rm", "it", "mbox", "hbox")
# Commands that ARE a space in typesetting. Stripping them without a trace
# would glue together words the author had separated.
_SPACE = ("quad", "qquad")
_WRAPPER = re.compile(r"^\s*(?:\\\[|\\\(|\$\$|\$)|(?:\\\]|\\\)|\$\$|\$)\s*$")
_HEAD = re.compile(r"\\(" + "|".join(_TYPEFACE) + r")(?![a-zA-Z])")
_SP = re.compile(r"\\(" + "|".join(_SPACE) + r")(?![a-zA-Z])")
_INDEX = re.compile(r"[_^]\{([^{}]*)\}")


def bare_math(s: str) -> str:
    """Strip wrapper and typeface off a LaTeX fragment, keeping command NAMES.

    A function, not a line inside `normalize`: with no seam the battery has
    nothing to break. Measured at `NORM_STEPS["latex"]`.
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
    # The NAME of a meaningful command survives: `\alpha` -> `alpha`.
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


# Rejections are PER LEVEL: `NORM_REFUSED` holds those of the CELL
# measurement, which says nothing about matching a formula against prose.
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
