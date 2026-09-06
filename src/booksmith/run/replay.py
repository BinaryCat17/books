"""Input snapshot: what it lacks for the run to be repeatable.

A run is unrepeatable by construction -- the card was rented for twenty
minutes and killed, the prompt lives in someone else's library, the weights sat
on a machine that is gone. The only trace is `run.json`, and it used to carry
ten fields: pages, seconds, pages/s, model, device, server, source, stem,
passes, cost_usd. No knob, no prompt, no package version, no weights
fingerprint, no code commit.

What that costs: "hieroglyphs under label `text` 8 per million characters,
under `table` 817" -- a hundredfold skew at one model on one page, and the only
difference between them was the prompt. No `run.json` of the six books can
confirm that, or say how the run of one book differed from another beyond the
file name.

Hence this registry. Not a wish list: every entry is a value without which the
run does not repeat, and says what it settles. `books replay --check` returns
**1** while the missing list is non-empty; a note in a report nobody reads
already existed once, and it read "run.json ought to have".

TWO SOURCES OF REQUIREMENTS, AND THE SECOND IS NOT HAND-TYPED. `_base()` holds
knob keys (from `knobs.names()`) and literals common to any writer. The other
is the ADAPTER FINGERPRINT, whose shape each adapter declares in its own
`fingerprint()`: paddle one way, yolox another, docling with a vendor-pipeline
branch holding two sha256 and a label map. Retyping it here would start a
second list -- the kind that parts with the code at the first model edit, as
the counts quoted in `composition()` once parted. So the shape is DERIVED by
parsing the source of the adapter the snapshot names, the way `knobs.readers()`
derives knob consumers by walking the tree.

WHAT PAID FOR THAT. The requirement used not to descend into the fingerprint
branch AT ALL. A docling snapshot lost the whole vendor-pipeline branch --
mode, docling version, BOTH vendor sha256, postprocess options, label map --
and the weights sha256 with it; the check printed "42 of 42 values, 0 missing"
and returned 0. Forty-two values proved the knob `DOCLING_PIPELINE` and nothing
else: what the run computed with, the snapshot was not obliged to say.

THE SHAPE CANNOT ALWAYS BE VERIFIED, AND SILENCE ABOUT THAT IS FORBIDDEN. The
snapshot carries the sha256 of the adapter file. It matches the tree -- the
shape came from THAT code, and every fingerprint value missing is an omission.
It does not -- the snapshot was taken by another adapter: "snapshot old", not
"snapshot incomplete". That gets its own line and its own number and does NOT
sink into the general "missing", or every old bench directory would burn a wall
of false omissions, and a wall that always burns is not a check.

FIVE TROUBLES, NOT ONE, EACH ON ITS OWN LINE. A value ABSENT (omission, code
1); PRESENT AND EMPTY (`null`, `[]`, `""` -- lawful: "no prompts at all", "the
build has no native threshold", but to be seen rather than assumed); with
NOTHING TO VERIFY IT AGAINST; NOT COVERED AT ALL; and the SHAPE NOT DERIVED,
the writer declaring `fingerprint()` while the walk gets no key out of it. The
last was silent and cost the instrument its face: an empty shape gave an empty
requirement, the branch never entered the list, and a snapshot with no
fingerprint whatsoever passed with "51 of 51 values, 0 missing" and the word
VERIFIED. Now the branch itself is required. Five numbers, five lines.

WHAT THIS CHECK CANNOT DO, WHICH MATTERS MORE. Parsing sees only keys written
out in LETTERS. Keys born during a run -- per-label thresholds, the label map,
the sha256 of each vendor file by name, the pipeline summary fields -- cannot
be derived, and such a value is cut unnoticed. `uncovered()` counts them and
both commands print the number: a blind spot named by a number and one kept
quiet are different things. It is closed at the writer -- let the adapter
declare their count beside them (`thresholds 25`) and loss shows by comparison.
Measured by cutting one at a time: a doclayout snapshot leaves 25 of 50
uncovered, docling with the pipeline on 49 of 80 (2026-08-29, two pages of
`bench/matematika`).

How much of what right now the commands and `composition()` print themselves:
numbers in prose age silently, as this header has already witnessed.
"""
import ast
import hashlib
import json
import os

from . import knobs

# Package root: adapter sources are looked up under it (see `_writer_file`).
PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The key the snapshot carries the adapter fingerprint under; `detect.py`
# writes it as `"fingerprint": fp`. The one value here not taken from the
# adapter source, so a rename at the writer shows at once: on a FRESH snapshot
# every derived requirement turns into an omission.
FP = "fingerprint"


def facts(outdir):
    """The run snapshot from `run.json`. An unreadable file is an empty snapshot.

    It used to live in `layout.facts`; that module went with the old product --
    `passes/`, `book.md`, `toc.md` described what is no longer built -- and
    reading one file does not earn a module.
    """
    # TWO PLACES, BOTH LAWFUL: a DETECTION directory keeps the snapshot at the
    # root, a BOOK directory in `assets/`, its root holding exactly one file --
    # the book. Looking at the root only, the check answered "no snapshot at
    # all" on a book whose snapshot sat one floor down: a talking step lying
    # with a zero, while `doc/html.py` promises verbatim that `books replay
    # --check` must return 0 there too. The kitchen directory name is asked of
    # the writer, not typed: a typed copy parts ways silently, as one has.
    from ..doc.html import ASSETS
    for f in (os.path.join(outdir, "run.json"),
              os.path.join(outdir, ASSETS, "run.json")):
        try:
            with open(f, encoding="utf-8") as fh:
                d = json.load(fh)
            if isinstance(d, dict):
                return d
        except (OSError, ValueError):
            continue
    return {}


# sha256 of the whole file, the same one `detect._sha256` writes into the
# snapshot. Ours rather than imported, on purpose: `replay` is a CHECK, and it
# must not fail because the `detect.py` it checks is broken.
def _sha256(path):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    except OSError:
        return None
    return h.hexdigest()


# The registry of values without which a run does not repeat.
#
# The key is a path in `run.json` (a tuple: the snapshot is nested). The
# presence rule is blunt -- **the key must exist**. `null` is a lawful answer
# ("no system message at all", "generation parameters were never set") and it
# is a VALUE; a missing key is an omission. "The prompt is empty" and "the
# prompt was never looked at" are different runs.
#
# Paths are spelled as the format spells them since the migration:
# `knobs/NAME/value`. Renaming that one path took `bench/annopage` from 38 of
# 55 values down to 16 WITHOUT moving the return code -- `rc` is 1 before the
# damage and after -- so the signal is in the magnitude alone.
def _base(knob_names):
    r = []
    for name in knob_names:
        r.append((("knobs", name, "value"), f"knob {name}"))
    r += [
        (("raster", "scale"), "raster scale"),
        (("raster", "dpi"), "raster resolution, dpi"),
        (("args",), "arguments of the recogniser run"),
        (("commit",), "the booksmith commit that counted"),
        (("source", "sha256"), "sha256 of the book's source file"),
        (("adapter", "sha256"), "sha256 of the model adapter"),
        (("adapter", "name"), "which model read"),
        # Prompts were once required by name, `ocr` and `table`, because the
        # old pipeline had those two. The adapter knows how many it has and
        # what they are called; required is that it write them down, not that
        # there be two.
        (("prompts",), "every adapter prompt, byte for byte"),
        (("generation", "temperature"), "generation temperature"),
        (("generation", "max_tokens"), "ceiling on answer length"),
        (("generation", "top_p"), "probability cutoff"),
        (("generation", "seed"), "generation seed"),
        (("packages",), "versions of the packages that decide parsing"),
        (("weights", "vl"), "VLM weights fingerprint"),
        (("weights", "layout"), "layout weights fingerprint"),
        (("repeat_command",), "the ready repeat line"),
    ]
    return tuple(r)


# --------------------------------------------------------------- fingerprint
# The shape is derived from the adapter source. Below is a walk of the python
# tree: literals only, no execution. Calling someone else's `fingerprint()`
# for its shape would raise an ONNX session and read the weights on EVERY
# check, and on a machine without weights the check would go blind silently.

def _classes(tree):
    return {n.name: n for n in tree.body if isinstance(n, ast.ClassDef)}


def _class_attr(cls, attr):
    """The value of a literal class attribute (`name = "docling-heron"`)."""
    for n in cls.body:
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant):
            for t in n.targets:
                if isinstance(t, ast.Name) and t.id == attr:
                    return n.value.value
    return None


def _fp_defs(tree):
    """Every `fingerprint` in the module: {class name: function node}."""
    out = {}
    for n in tree.body:
        if isinstance(n, ast.ClassDef):
            for m in n.body:
                if isinstance(m, ast.FunctionDef) and m.name == "fingerprint":
                    out[n.name] = m
    return out


def _fp_def(tree, cls_name):
    """The `fingerprint` of the class or of its ancestor WITHIN the module.

    Inheritance counts: `DoclingEgret(DoclingHeron)` writes no fingerprint of
    its own, and without walking the bases an egret run would come out with an
    empty shape -- unverifiable, and silently so.
    """
    cs, defs, seen = _classes(tree), _fp_defs(tree), set()
    while cls_name in cs and cls_name not in seen:
        seen.add(cls_name)
        if cls_name in defs:
            return defs[cls_name], cls_name
        nxt = None
        for b in cs[cls_name].bases:
            if isinstance(b, ast.Name) and b.id in cs:
                nxt = b.id
                break
        cls_name = nxt
    return None, None


def _paths(expr, tree, cls, depth=0):
    """The paths this expression will CERTAINLY put into the snapshot."""
    if depth > 8:
        return set()
    if isinstance(expr, ast.Dict):
        out = set()
        for k, v in zip(expr.keys, expr.values):
            # `**other_dict` is skipped: its keys are invisible from here,
            # and an invented key is worse than an unnamed one.
            if not (isinstance(k, ast.Constant) and isinstance(k.value, str)):
                continue
            out.add((k.value,))
            out |= {(k.value,) + p for p in _paths(v, tree, cls, depth + 1)}
        return out
    if isinstance(expr, ast.IfExp):
        # The INTERSECTION of the branches, not their union: the docling
        # `docling_pipeline` branch has DIFFERENT keys per branch -- `classes`
        # and `label_outward` with the pipeline on, absent with it off. A union
        # would demand of a `DOCLING_PIPELINE=off` run values that never exist
        # there, failing on a healthy snapshot, and such a check gets switched
        # off.
        return (_paths(expr.body, tree, cls, depth + 1)
                & _paths(expr.orelse, tree, cls, depth + 1))
    if isinstance(expr, ast.Call):
        f = expr.func
        if isinstance(f, ast.Attribute) and f.attr == "fingerprint":
            # A nested fingerprint (at docling, the vendor pipeline). Whose
            # exactly is invisible from `self._pipe`, so we take the module's
            # one other `fingerprint` and stay silent at two or more: there is
            # nothing to guess from.
            cand = [(c, n) for c, n in _fp_defs(tree).items() if c != cls]
            if len(cand) == 1:
                return _returned(cand[0][1], tree, cand[0][0], depth + 1)
        return set()
    return set()


def _returned(fn, tree, cls, depth=0):
    """Paths from all the `return`s of a function -- intersected, not first."""
    rs = [n for n in ast.walk(fn)
          if isinstance(n, ast.Return) and n.value is not None]
    if not rs:
        return set()
    out = _paths(rs[0].value, tree, cls, depth)
    for r in rs[1:]:
        out &= _paths(r.value, tree, cls, depth)
    return out


def _sources():
    for root, dirs, files in os.walk(PKG):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for n in sorted(files):
            if n.endswith(".py"):
                yield os.path.join(root, n)


def _parse(path):
    try:
        with open(path, encoding="utf-8") as f:
            return ast.parse(f.read())
    except (OSError, SyntaxError, ValueError):
        return None


def _writer_file(mod, name):
    """The snapshot writer's file: by module name, else by adapter name.

    `detect.py` puts the module name in (field `adapter/module`); old snapshots
    lack it, and then the writer is found by the declared `name =
    "doclayout-onnx"` in the class. Identification, not verification: whether
    the code matches is settled by the sha256 below.

    Returns (file, how identified, every file matched). More than one match is
    not identified: taking "the first one" would check the fingerprint against
    someone else's code and call that verification.
    """
    if isinstance(mod, str) and mod.split(".")[:1] == ["booksmith"]:
        p = os.path.join(PKG, *mod.split(".")[1:]) + ".py"
        if os.path.exists(p):
            return p, "by module name", [p]
    hits = []
    if isinstance(name, str) and name:
        for p in _sources():
            tree = _parse(p)
            if tree is None:
                continue
            if any(_class_attr(c, "name") == name
                   for c in _classes(tree).values()):
                hits.append(p)
    if len(hits) == 1:
        return hits[0], "by adapter name", hits
    return None, None, hits


def shape(snap):
    """The adapter fingerprint shape derived from source, and what verified it.

    Returns the `derived` requirements, the counts `not_verified` and `blind`,
    and a ready line for the log. The counts differ on purpose: `not_verified`
    is "shape derived, but not from the code that computed" (snapshot old),
    `blind` is "the writer cannot be identified at all" -- there not even the
    amount left unchecked is knowable.
    """
    r = {"name": None, "file": None, "how": None, "verified": False,
         "derived": [], "not_verified": 0, "of_those_missing": 0, "blind": 0,
         "not_derived": 0, "row": ""}
    if not snap:
        r["row"] = "fingerprint: there is no snapshot -- nothing to check"
        return r
    ad = snap.get("adapter")
    ad = ad if isinstance(ad, dict) else {}
    name = ad.get("name")
    r["name"] = name
    said = ad.get("sha256")
    said_s = str(said)[:8] if isinstance(said, str) else "not recorded"
    path, how, hits = _writer_file(ad.get("module"), name)
    if path is None:
        r["blind"] = 1
        r["row"] = (
            f"fingerprint NOT VERIFIED: writer {name!r} not identified -- "
            + (f"the name is declared in {len(hits)} files of the tree "
               f"({', '.join(os.path.relpath(h, PKG) for h in hits)})"
               if hits else
               "the snapshot named no adapter/module field, and the tree "
               "holds no class of that name")
            + ". How many fingerprint values went unchecked is unknown too")
        return r
    r["file"], r["how"] = path, how
    rel = os.path.relpath(path, PKG)
    now = _sha256(path)
    tree = _parse(path)
    owner = _owner_class(tree, name) if tree else None
    fn, def_cls = _fp_def(tree, owner) if owner else (None, None)
    if tree is None or (owner is None and _fp_defs(tree)):
        # The file was found, but WHO in it wrote the fingerprint is unknown:
        # no class carries that `name`, and the file holds more than one
        # `fingerprint`. Taking any would check the shape against a foreign
        # class.
        r["blind"] = 1
        r["row"] = (f"fingerprint NOT VERIFIED: {rel} holds no class with "
                       f"name = {name!r}, and it holds more than one "
                       f"`fingerprint` -- nothing tells whose fingerprint "
                       f"lies in the snapshot")
        return r
    if fn is None:
        ok_fp, fpv = _dig(snap, (FP,))
        if ok_fp and isinstance(fpv, dict) and fpv:
            # The snapshot HAS a fingerprint and today's writer has none:
            # the code has moved since the run. Saying "no fingerprint at all"
            # here would declare someone else's branch a value.
            r["blind"] = 1
            r["row"] = (
                f"fingerprint NOT VERIFIED: the snapshot has one "
                f"({len(fpv)} branches), and writer {name} ({rel}) declares "
                f"no `fingerprint()` at all -- the code has parted from the "
                f"run, there is nothing to check against")
            return r
        # A writer without `fingerprint()` -- that is how `doc.html` writes
        # its snapshot: assembling HTML is not a model and gives no
        # fingerprint. A VALUE, not an omission.
        r["verified"] = True
        r["row"] = (f"no fingerprint at all: {name} ({rel}) wrote it and "
                       f"declares no `fingerprint()` -- this is a value, "
                       f"not an omission")
        return r
    keys = sorted(_returned(fn, tree, def_cls))
    if not keys:
        # THE SHAPE WAS NOT DERIVED -- A LOUD VALUE, NOT CONSENT. The writer
        # declares `fingerprint()` (else we left by the branch above) and the
        # walk got no key out of it: so it goes when the fingerprint is built
        # by a comprehension, behind a loop, or returned as a field assembled
        # earlier. Silence here used to approve such a snapshot with code 0
        # (see the header). So we demand the FLOOR, the branch itself -- what
        # is inside is invisible from here -- and name the ignorance by a
        # number. NOT "no fingerprint at all": that case left by the branch
        # above, declared a value.
        r["not_derived"] = 1
        r["derived"] = [((FP,), f"the whole fingerprint of adapter {name}")]
        r["row"] = (
            f"THE FINGERPRINT SHAPE OF ADAPTER {name} WOULD NOT DERIVE: "
            f"`fingerprint()` is declared in {rel}, and the walk got not one "
            f"key out of it (sha256 "
            + ("matches" if isinstance(said, str) and now == said
               else f"does NOT match: snapshot {said_s}, tree "
                    f"{str(now)[:8]}")
            + f"). Only the {FP} branch itself is required, and what is "
              f"inside is checked by nothing: the snapshot holds "
              f"{len(_fp_paths(snap))} values there, and any one of them can "
              f"be cut unnoticed")
        return r
    req = [((FP,) + k, f"a fingerprint value of adapter {name}") for k in keys]
    req.insert(0, ((FP,), f"the whole fingerprint of adapter {name}"))
    if isinstance(said, str) and now == said:
        r["verified"] = True
        r["derived"] = req
        r["row"] = (f"the fingerprint of adapter {name} is verified: {rel} "
                       f"is the very one (sha256 matches, identified {how}), "
                       f"{len(req)} values were derived from it")
        return r
    # Nothing to verify against -- but HOW MUCH of today's shape the snapshot
    # holds can still be said, and these are different tidings. "26 not
    # verified, 0 absent" means the old snapshot carries everything today's
    # code writes; "32 not verified, 9 absent" means nine are not there, and
    # whether they were cut or never existed is invisible from here. The number
    # is printed, the conclusion is not drawn: a guess in a return code is the
    # same lie as silence.
    r["not_verified"] = len(req)
    r["of_those_missing"] = sum(1 for path, _ in req if not _dig(snap, path)[0])
    r["row"] = (
        f"the fingerprint of adapter {name} is NOT VERIFIED: {rel} is not the "
        f"code that counted (snapshot {said_s}, tree {str(now)[:8]}) -- "
        f"{len(req)} fingerprint values went unchecked, and "
        f"{r['of_those_missing']} of them are absent from the snapshot. This "
        f"is 'snapshot OLD', not 'snapshot INCOMPLETE'")
    return r


def _owner_class(tree, name):
    """The adapter class in the module: by declared `name`, else the only one."""
    for cname, c in _classes(tree).items():
        if _class_attr(c, "name") == name:
            return cname
    defs = _fp_defs(tree)
    return next(iter(defs)) if len(defs) == 1 else None


# Knob names come from the registry, they are not retyped here. Two lists of
# knobs are two lists that will part; they already had (`_PASS` held 13 of 17).
def knob_names():
    return knobs.names()


def required(snap=None, sh=None):
    """Requirements: the common ones plus those derived from this snapshot's adapter.

    With no snapshot, only the common ones: whose fingerprint to demand is
    unknown before `run.json` is read, and demanding "some" would be inventing.
    """
    req = list(_base(knob_names()))
    if snap:
        sh = shape(snap) if sh is None else sh
        req += sh["derived"]
    return tuple(req)


def composition(req=None):
    """What the requirement is made of: (knob keys, literals, fingerprint).

    The numbers are COUNTED. The `selfcheck` docstring below used to say "28
    requirements of 36 ... twenty keys laid out by knobs.snapshot() ... eight
    more are literals", and by 2026-08-29 not one of the three held: the knob
    registry grew and the text beside it was not recounted. The third term
    cannot be a number in prose at all -- every adapter has its own
    fingerprint.
    """
    req = required() if req is None else req
    kn = sum(1 for p, _ in req if p and p[0] == "knobs")
    fp = sum(1 for p, _ in req if p and p[0] == FP)
    return kn, len(req) - kn - fp, fp


def _dig(d, path):
    """Whether the snapshot holds this path. Returns (present, value)."""
    cur = d
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            return False, None
        cur = cur[k]
    return True, cur


def missing(snap, req=None):
    """What the snapshot lacks. Pairs of (path, what it settles)."""
    out = []
    for path, what in (req if req is not None else required()):
        ok, _ = _dig(snap, path)
        if not ok:
            out.append((path, what))
    return out


def _empty(v):
    return v is None or (isinstance(v, (str, bytes, list, tuple, dict))
                         and len(v) == 0)


def hollow(snap, req=None):
    """Values that ARE there but empty. A separate trouble, a separate number.

    Empty is lawful: a detector has no prompts, the heron build no native
    threshold, a knob may have no value. But "empty" and "absent" cure
    different things and must not be added together: only an omission raises
    the return code, the empty prints as a number -- so a gutted branch
    (`docling_pipeline` replaced by `{}`) is as visible as a cut one.
    """
    out = []
    for path, what in (req if req is not None else required()):
        ok, v = _dig(snap, path)
        if ok and _empty(v):
            out.append((path, what))
    return out


def _fp_paths(snap):
    """Every path inside the fingerprint branch of THE SNAPSHOT (not of the requirement)."""
    ok, fp = _dig(snap, (FP,))
    if not ok or not isinstance(fp, dict):
        return set()
    have = set()

    def walk(node, pre):
        for k, v in node.items():
            have.add(pre + (k,))
            if isinstance(v, dict):
                walk(v, pre + (k,))

    walk(fp, (FP,))
    return have


def uncovered(snap, sh):
    """Fingerprint values the snapshot HAS and the requirement did not cover.

    The blind spot of shape derivation, named by a number. It comes from the
    branching: shapes are derived by INTERSECTING branches (see `_paths`), so a
    value living in one branch only -- what `docling_pipeline` writes at `full`
    and not at `off` -- goes uncovered, and can be cut unnoticed.
    """
    if not sh.get("verified"):
        return []
    return sorted(_fp_paths(snap) - {path for path, _ in sh["derived"]})


def check(outdir, verbose=True):
    """Whether the parse snapshot is complete. Returns the list of what is missing."""
    snap = facts(outdir)
    sh = shape(snap)
    req = required(snap, sh)
    miss = missing(snap, req)
    hol = hollow(snap, req)
    if verbose:
        name = os.path.relpath(outdir)
        if not snap:
            print(f"{name}: run.json does not read -- no snapshot at all")
        kn_h = sum(1 for p, _ in hol if p and p[0] == "knobs")
        # The caveat stands ON THE SAME LINE as the number: "42 of 42, 0
        # missing" with the explanation a line below reads as "complete", and a
        # snapshot with an unverified fingerprint is not complete but
        # unchecked.
        caveat = ""
        if sh["not_verified"]:
            caveat = (f"; NOT EVERYTHING WAS CHECKED -- "
                      f"{sh['not_verified']} fingerprint values have nothing "
                      f"to be checked against")
        elif sh["blind"]:
            caveat = ("; NOT EVERYTHING WAS CHECKED -- the fingerprint was "
                      "not verified at all")
        elif sh["not_derived"]:
            # Same caveat, different trouble: the writer is identified and has
            # a fingerprint whose shape would not derive. Only the branch
            # itself is required, and silence about that once approved a
            # snapshot with no fingerprint at all.
            caveat = ("; NOT EVERYTHING WAS CHECKED -- the fingerprint "
                      "shape would not derive, only the branch is required")
        print(f"{name}: values in the snapshot {len(req) - len(miss)} of "
              f"{len(req)}, missing {len(miss)}, empty {len(hol)} "
              f"(of those, knobs with no value {kn_h}){caveat}")
        print(f"  {sh['row']}")
        unc = uncovered(snap, sh)
        if unc:
            names = [" / ".join(p[1:]) for p in unc[:5]]
            print(f"  NOT covered by the requirement: {len(unc)} "
                  f"fingerprint values of the {len(_fp_paths(snap))} lying "
                  f"in the snapshot -- their keys are born during a run "
                  f"(per-label thresholds, translation maps, summaries) and "
                  f"cannot be derived from the source, so such a value can "
                  f"be cut unnoticed. "
                  + ", ".join(names)
                  + (f" and {len(unc) - 5} more" if len(unc) > 5 else ""))
        for path, what in miss:
            print(f"  absent {'/'.join(map(str, path)):43s} -- {what}")
        # Empty knobs are not listed by name: an empty string in a knob is the
        # ordinary "not set", there are always many, and they would drown the
        # list. Their number is above.
        for path, what in hol:
            if path and path[0] == "knobs":
                continue
            print(f"  empty {'/'.join(map(str, path)):44s} -- {what}")
    return miss


def selfcheck(outdir, log=print) -> int:
    """Can the check fail at all. Returns the number of omissions NOT caught.

    Why. The presence rule is "the key exists", and everything required is
    written unconditionally: knob keys wholesale by `knobs.snapshot()` (which
    enumerates the whole registry by construction), the rest as literals in
    `detect.py` and `doc/html.py`, the fingerprint values by the adapter
    itself. So on the project's OWN output `check` cannot return 1 for any
    input, and its ability to fail had never been shown, though the project
    rule demands exactly that.

    We knock out each required key in turn and confirm `missing` noticed. The
    opposite trouble is caught too: a path the snapshot never had cannot be
    knocked out, and is named separately.

    SIX TROUBLES, SIX NUMBERS, ONE SUM IN THE RETURN. An omission not caught
    (the check is asleep), a key absent from the start (the writer does not lay
    it), knob registry drift against the source tree (`knobs.audit()`),
    fingerprint values with nothing to verify against (another adapter took the
    snapshot), an unidentified writer (nothing to verify with at all), and a
    shape not derived. Separate magnitudes in the log; they add up only at the
    exit, because they fall silent alike -- without a return code any of them
    stays a note nobody reads. A returned zero means "asked and not found", not
    "not asked": an unreadable `run.json` returns len(req), a shape with
    nothing to verify against returns the count of unverified values, and a
    shape that would not derive returns one, not silence.

    THE SEVENTH NUMBER IS PRINTED BUT NOT SUMMED, by decision: fingerprint
    values whose keys are born during a run (`uncovered()`) are cut unnoticed,
    but that is fixed at the WRITER, and there are fifty of them on every
    healthy docling run. Summed in, the command would burn always -- and a
    check that always burns reports nothing and gets switched off. So the
    number stands beside, and the return code stays about what a snapshot can
    be fixed for.
    """
    snap = facts(outdir)
    sh = shape(snap)
    req = required(snap, sh)
    name = os.path.relpath(outdir)
    kn, lit, fp = composition(req)
    # Registry drift is looked for before the snapshot: it is about the
    # sources, not the run output, and an unreadable `run.json` is no reason to
    # keep quiet about it.
    drift = knobs.audit()
    for line_ in drift:
        log(f"  KNOB REGISTRY: {line_}")
    log(f"{name}: requirements {len(req)} = knob keys {kn} + literals "
        f"{lit} + fingerprint values {fp}; knobs in the registry "
        f"{len(knobs.names())}, of those declared a debt "
        f"{len(knobs.debts())}; registry drift against the tree {len(drift)}")
    log(f"  {sh['row']}")
    unc = uncovered(snap, sh)
    if unc:
        log(f"  fingerprint values that can be cut unnoticed: {len(unc)} "
            f"-- their keys are born during a run (per-label thresholds, "
            f"translation maps, pipeline summaries), and parsing the source "
            f"does not see them. This is the WRITER's blind spot, not the "
            f"check's: it closes by the adapter declaring their count beside "
            f"them -- which is why it is printed as a number")
    if not snap:
        log(f"{name}: run.json does not read -- nothing to knock out")
        return len(req) + len(drift)
    absent = [p for p, _ in req if not _dig(snap, p)[0]]
    bad = 0
    for path, what in req:
        if path in absent:
            continue
        cut = json.loads(json.dumps(snap))
        cur = cut
        for k in path[:-1]:
            cur = cur[k]
        del cur[path[-1]]
        if not any(p == path for p, _ in missing(cut, req)):
            log(f"  NOT CAUGHT: {'/'.join(map(str, path))} -- {what}")
            bad += 1
    log(f"{name}: knocked out {len(req) - len(absent)} keys of "
        f"{len(req)}, omissions not caught {bad}"
        + (f"; absent from the start {len(absent)}" if absent else "")
        + (f"; fingerprint values with nothing to check against "
           f"{sh['not_verified']}" if sh["not_verified"] else "")
        + ("; the snapshot's writer was not identified" if sh["blind"] else "")
        + ("; the fingerprint shape would not derive -- only the branch "
           "itself was required" if sh["not_derived"] else ""))
    return (bad + len(absent) + len(drift) + sh["not_verified"] + sh["blind"]
            + sh["not_derived"])


def line(outdir):
    """The ready repeat command line, if one was written down."""
    v = facts(outdir).get("repeat_command")
    return v if isinstance(v, str) else None


def cmd_replay(a):
    """`books replay [--check] <directory>...`

    Without `--check` it prints the repeat line; with it, what the snapshot
    lacks, returning 1 if anything at all is missing. The return code is not
    decoration: it is there so the check can stop something -- a run, a build,
    itself.
    """
    dirs = a.outdir or []
    rc = 0
    for d in dirs:
        if getattr(a, "selfcheck", False):
            if selfcheck(d):
                rc = 1
        elif a.check:
            if check(d):
                rc = 1
        else:
            v = line(d)
            if v:
                print(v)
            else:
                print(f"{os.path.relpath(d)}: there is no repeat line -- "
                      f"the snapshot is incomplete, see books replay --check")
                rc = 1
    return rc
