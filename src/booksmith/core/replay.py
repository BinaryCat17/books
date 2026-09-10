"""Input snapshot: what it lacks for the run to be repeatable.

Every entry of the registry is a value without which the run does not repeat,
and says what it settles; `books replay --check` returns 1 while the missing
list is non-empty. Requirements come from `_base()` -- the knob keys and the
literals common to any writer -- and from the adapter fingerprint, whose shape
is derived by parsing the source of the adapter the snapshot names.

Five troubles, each with its own line and its own number: absent (the only one
that moves the return code), present and empty, nothing to verify it against,
not covered by the requirement at all, and a shape that would not derive.
"""
import ast
import hashlib
import json
import os

from booksmith.core import knobs
from booksmith.core.log import log

# Package root: adapter sources are looked up under it (see `_writer_file`).
PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The key the snapshot carries the adapter fingerprint under, and the one value
# here not taken from the adapter source, so a rename at the writer shows at once.
FP = "fingerprint"


def facts(outdir):
    """The run snapshot from `run.json`. An unreadable file is an empty snapshot."""
    # Two places, both lawful: a detect run keeps the snapshot at its root, a book
    # directory in `assets/`, whose name is asked of the writer rather than typed.
    from booksmith.core.book import ASSETS
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


# sha256 of the whole file, ours rather than imported: a check must not fail
# because the code it checks is broken.
def _sha256(path):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    except OSError:
        return None
    return h.hexdigest()


# The registry. A key is a path in the nested `run.json`, and the rule is blunt:
# the key must exist. `null` is a lawful value; a missing key is an omission.
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
        # The adapter knows how many prompts it has; required is that it write them down.
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
# The shape is derived from the adapter source by a walk of the python tree,
# literals only: calling its `fingerprint()` would raise an ONNX session.

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
    """The `fingerprint` of the class or of its ancestor within the module.

    Inheritance counts: `DoclingEgret(DoclingHeron)` declares none of its own,
    and without walking the bases an egret run would derive an empty shape.
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
        for k, v in zip(expr.keys, expr.values, strict=True):
            # `**other_dict` is skipped: an invented key is worse than an unnamed one.
            if not (isinstance(k, ast.Constant) and isinstance(k.value, str)):
                continue
            out.add((k.value,))
            out |= {(k.value,) + p for p in _paths(v, tree, cls, depth + 1)}
        return out
    if isinstance(expr, ast.IfExp):
        # The intersection of the branches, not their union: `docling_pipeline`
        # has different keys per branch, and a union would fail a healthy snapshot.
        return (_paths(expr.body, tree, cls, depth + 1)
                & _paths(expr.orelse, tree, cls, depth + 1))
    if isinstance(expr, ast.Call):
        f = expr.func
        if isinstance(f, ast.Attribute) and f.attr == "fingerprint":
            # A nested fingerprint (the vendor pipeline at docling). Whose it is
            # is invisible from `self._pipe`, so at two or more we stay silent.
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
    """The snapshot writer's file: by module name (`adapter/module`), else by the
    class's declared `name`. Identification, not verification -- the sha256 below
    settles that. Returns (file, how, every match); several is not identified.
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

    `not_verified` is "shape derived, but not from the code that computed";
    `blind` is "the writer is not identified", where the amount is unknown too.
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
        # The file was found, but who in it wrote the fingerprint is unknown, and
        # taking any of several would check the shape against a foreign class.
        r["blind"] = 1
        r["row"] = (f"fingerprint NOT VERIFIED: {rel} holds no class with "
                       f"name = {name!r}, and it holds more than one "
                       f"`fingerprint` -- nothing tells whose fingerprint "
                       f"lies in the snapshot")
        return r
    if fn is None:
        ok_fp, fpv = _dig(snap, (FP,))
        if ok_fp and isinstance(fpv, dict) and fpv:
            # The snapshot has a fingerprint and today's writer has none: the code
            # has parted from the run, and there is nothing to check against.
            r["blind"] = 1
            r["row"] = (
                f"fingerprint NOT VERIFIED: the snapshot has one "
                f"({len(fpv)} branches), and writer {name} ({rel}) declares "
                f"no `fingerprint()` at all -- the code has parted from the "
                f"run, there is nothing to check against")
            return r
        # A writer without `fingerprint()`: assembling HTML is not a model, and
        # that is a value, not an omission.
        r["verified"] = True
        r["row"] = (f"no fingerprint at all: {name} ({rel}) wrote it and "
                       f"declares no `fingerprint()` -- this is a value, "
                       f"not an omission")
        return r
    keys = sorted(_returned(fn, tree, def_cls))
    if not keys:
        # The shape would not derive: the writer declares `fingerprint()` and the
        # walk got no key out of it, so only the branch itself is required.
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
    # Nothing to verify against, but how much of today's shape the snapshot holds
    # can still be said: the number is printed, the conclusion is not drawn.
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


# Knob names come from the registry: two lists of knobs are two lists that part.
def knob_names():
    return knobs.names()


def required(snap=None, sh=None):
    """Requirements: the common ones plus those derived from this snapshot's adapter.

    With no snapshot, only the common ones: whose fingerprint to demand is
    unknown before `run.json` is read.
    """
    req = list(_base(knob_names()))
    if snap:
        sh = shape(snap) if sh is None else sh
        req += sh["derived"]
    return tuple(req)


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
    """Values that are there but empty. A separate trouble, a separate number.

    Empty is lawful -- a detector has no prompts, a knob may have no value -- but
    only an omission raises the return code, so a gutted branch stays visible.
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
    """Fingerprint values the snapshot has and the requirement did not cover.

    The blind spot of shape derivation, named by a number: shapes are derived by
    intersecting branches, so a value in one branch only can be cut unnoticed.
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
            log(f"{name}: run.json does not read -- no snapshot at all")
        kn_h = sum(1 for p, _ in hol if p and p[0] == "knobs")
        # The caveat stands on the same line as the number, or "0 missing" reads
        # as complete where the fingerprint was merely never checked.
        caveat = ""
        if sh["not_verified"]:
            caveat = (f"; NOT EVERYTHING WAS CHECKED -- "
                      f"{sh['not_verified']} fingerprint values have nothing "
                      f"to be checked against")
        elif sh["blind"]:
            caveat = ("; NOT EVERYTHING WAS CHECKED -- the fingerprint was "
                      "not verified at all")
        elif sh["not_derived"]:
            # Same caveat, another trouble: the writer is identified and its
            # fingerprint shape would not derive, so only the branch is required.
            caveat = ("; NOT EVERYTHING WAS CHECKED -- the fingerprint "
                      "shape would not derive, only the branch is required")
        log(f"{name}: values in the snapshot {len(req) - len(miss)} of "
              f"{len(req)}, missing {len(miss)}, empty {len(hol)} "
              f"(of those, knobs with no value {kn_h}){caveat}")
        log(f"  {sh['row']}")
        unc = uncovered(snap, sh)
        if unc:
            names = [" / ".join(p[1:]) for p in unc[:5]]
            log(f"  NOT covered by the requirement: {len(unc)} "
                  f"fingerprint values of the {len(_fp_paths(snap))} lying "
                  f"in the snapshot -- their keys are born during a run "
                  f"(per-label thresholds, translation maps, summaries) and "
                  f"cannot be derived from the source, so such a value can "
                  f"be cut unnoticed. "
                  + ", ".join(names)
                  + (f" and {len(unc) - 5} more" if len(unc) > 5 else ""))
        for path, what in miss:
            log(f"  absent {'/'.join(map(str, path)):43s} -- {what}")
        # Empty knobs are not listed by name: there are always many, and an empty
        # string is the ordinary "not set"; their number is above.
        for path, what in hol:
            if path and path[0] == "knobs":
                continue
            log(f"  empty {'/'.join(map(str, path)):44s} -- {what}")
    return miss


def line(outdir):
    """The ready repeat command line, if one was written down."""
    v = facts(outdir).get("repeat_command")
    return v if isinstance(v, str) else None


def cmd_replay(a):
    """`books replay [--check] <directory>...`

    Without `--check` it prints the repeat line; with it, what the snapshot
    lacks, returning 1 if anything is missing, so the check can stop something.
    """
    dirs = a.outdir or []
    rc = 0
    for d in dirs:
        if a.check:
            if check(d):
                rc = 1
        else:
            v = line(d)
            if v:
                log(v)
            else:
                log(f"{os.path.relpath(d)}: there is no repeat line -- "
                      f"the snapshot is incomplete, see books replay --check")
                rc = 1
    return rc
