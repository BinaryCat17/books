"""Can the snapshot check fail, and does the knob registry match the tree.

Two instruments that walk the source rather than a run's output. `readers` and
`audit` ask who really reads each knob; `knockout` and `selfcheck` cut each
required key out of a snapshot in turn and demand `replay.missing` notice.

Both exist because the obvious guard cannot see the thing: a knob the shell
exports never passes through `knob()`, and a presence rule of "the key is there"
cannot return 1 for any input the project itself writes.
"""
import json
import os
import re

import support
from booksmith.core.log import log
from booksmith.core import knobs, replay

SRC = support.SRC


def composition(req):
    """What the requirement is made of: (knob keys, literals, fingerprint)."""
    kn = sum(1 for p, _ in req if p and p[0] == "knobs")
    fp = sum(1 for p, _ in req if p and p[0] == replay.FP)
    return kn, len(req) - kn - fp, fp


def readers(root=None):
    """Who really reads each knob, by walking the tree: `knob("NAME")` and
    `number("NAME")` in `.py`, `$NAME` and `${NAME}` in `.sh`. A read through a
    variable looks dead -- a false alarm is the cheaper bias. Registry skipped."""
    root = root or SRC
    me = os.path.abspath(knobs.__file__)
    found = {k.name: [] for k in knobs.KNOBS}
    sh = {n: re.compile(r"\$\{?" + re.escape(n) + r"\b") for n in found}
    for dirpath, dirnames, files in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for fn in sorted(files):
            if not fn.endswith((".py", ".sh")):
                continue
            path = os.path.join(dirpath, fn)
            if os.path.abspath(path) == me:
                continue
            try:
                with open(path, encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
            except OSError:
                continue
            rel = os.path.relpath(path, root)
            py = fn.endswith(".py")
            for name in found:
                # Both spellings: `number("NAME")` reads a numeric knob.
                hit = (any(f'{fn_}("{name}")' in text
                           or f"{fn_}('{name}')" in text
                           or f'{fn_}("{name}",' in text
                           or f"{fn_}('{name}'," in text
                           for fn_ in ("knob", "number"))
                       if py else sh[name].search(text) is not None)
                if hit:
                    found[name].append(rel)
    return {n: tuple(v) for n, v in found.items()}


def audit(root=None):
    """Declared debt against what the tree holds. Empty means they agree: either
    `debt=True` stayed on a knob that is read again, or the last consumer went
    with its code while the knob stayed standing as alive."""
    who = readers(root)
    out = []
    for k in knobs.KNOBS:
        seen = who[k.name]
        if k.debt and seen:
            out.append(f"{k.name}: declared a debt (debt=True), and yet "
                       f"{', '.join(seen)} reads it -- drop the mark")
        if not k.debt and not seen:
            out.append(f"{k.name}: not one consumer found -- either it was "
                       f"lost together with its code, or set debt=True")
    return out


def knockout(snap, req):
    """Cut each required key in turn and see that `replay.missing` notices.
    Returns (omissions not caught, keys absent from the start): the first is the
    only number about the check, the second is about the snapshot."""
    absent = [p for p, _ in req if not replay._dig(snap, p)[0]]
    bad = 0
    for path, what in req:
        if path in absent:
            continue
        cut = json.loads(json.dumps(snap))
        cur = cut
        for k in path[:-1]:
            cur = cur[k]
        del cur[path[-1]]
        if not any(p == path for p, _ in replay.missing(cut, req)):
            log(f"  NOT CAUGHT: {'/'.join(map(str, path))} -- {what}")
            bad += 1
    return bad, absent


def selfcheck(outdir) -> int:
    """Can the check fail at all: the sum of six troubles, each printed apart --
    they fall silent alike, so they add up only at the exit, and a zero means
    "asked and not found". A seventh prints unsummed: it is fixed at the writer."""
    snap = replay.facts(outdir)
    sh = replay.shape(snap)
    req = replay.required(snap, sh)
    name = os.path.relpath(outdir)
    kn, lit, fp = composition(req)
    # Registry drift is looked for before the snapshot: it is about the
    # sources, and an unreadable `run.json` is no reason to keep quiet about it.
    drift = audit()
    for line_ in drift:
        log(f"  KNOB REGISTRY: {line_}")
    log(f"{name}: requirements {len(req)} = knob keys {kn} + literals "
        f"{lit} + fingerprint values {fp}; knobs in the registry "
        f"{len(knobs.names())}, of those declared a debt "
        f"{len(knobs.debts())}; registry drift against the tree {len(drift)}")
    log(f"  {sh['row']}")
    unc = replay.uncovered(snap, sh)
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
    bad, absent = knockout(snap, req)
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


# ------------------------------------------------------------- the registry

def test_audit_finds_no_disagreement():
    """The declared debt agrees with the source tree."""
    bad = audit()
    assert bad == [], ("the registry diverged from the tree, differences "
                       f"{len(bad)}:\n  " + "\n  ".join(bad))


def test_readers_finds_consumers_and_counts_them():
    """Counted, not remembered: live knobs must be exactly the total minus the
    knobs declared a debt."""
    who = readers()
    assert set(who) == set(knobs.names())
    live = sum(1 for v in who.values() if v)
    assert live == len(knobs.KNOBS) - len(knobs.debts()), (
        f"knobs {len(knobs.KNOBS)}, a consumer was found for {live}, "
        f"declared debt {len(knobs.debts())} -- the three do not add up")
    for name in knobs.debts():
        assert knobs.KNOB[name].debt is True
        assert not who[name], f"{name}: declared a debt, and {who[name]} reads it"


def test_docling_pipeline_is_registered():
    """The knob that decided 5826 boxes must be in the registry."""
    k = knobs.KNOB["DOCLING_PIPELINE"]
    assert k.debt is False, "a live knob is marked a debt"
    assert readers()["DOCLING_PIPELINE"], (
        "DOCLING_PIPELINE has not one consumer")


# --------------------------------------------------------- the derived shape
# `replay.shape` derives the required fingerprint shape by parsing the adapter's
# source. Parsing is sometimes powerless -- a fingerprint built by a
# comprehension, past a loop, handed over ready -- and then the branch itself
# must still be required, or a snapshot with no fingerprint passes with code 0.

def _adapter_with_underivable_fingerprint(tmp):
    """A snapshot writer whose shape tree-parsing will not derive: a declared
    `name` and a declared `fingerprint()` whose keys are counted during a run."""
    path = os.path.join(tmp, "myocr.py")
    with open(path, "w", encoding="utf-8") as f:
        f.write("class MyOcr:\n"
                "    name = \"myocr\"\n\n"
                "    def fingerprint(self):\n"
                "        return {k: v for k, v in self._parts.items()}\n")
    return path


def _tmp_out(tmp, snap):
    """The directory with `run.json` -- what `selfcheck` reads."""
    out = os.path.join(tmp, "out")
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "run.json"), "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False)
    return out


def test_shape_that_could_not_be_derived_is_loud_not_silent():
    """Failure to derive the shape is a value, not silent agreement: at least the
    fingerprint branch is required, and the ignorance is named by a number, or
    "all checked" and "as much as we could" are indistinguishable."""
    import shutil as _sh
    import tempfile

    tmp = tempfile.mkdtemp(prefix="booksmith-shape-")
    was = replay.PKG
    try:
        path = _adapter_with_underivable_fingerprint(tmp)
        replay.PKG = tmp
        snap = {}
        for p, _ in replay._base(knobs.names()):
            cur = snap
            for k in p[:-1]:
                cur = cur.setdefault(k, {})
            cur[p[-1]] = "present"
        snap["adapter"] = {"name": "myocr", "module": "booksmith.myocr",
                           "sha256": replay._sha256(path)}
        assert replay.FP not in snap, "the fingerprint branch is not put there by us"
        sh = replay.shape(snap)
        assert sh["not_derived"] == 1, (
            "the fingerprint's shape could not be derived and the "
            "instrument keeps quiet: silence here reads as \"everything was "
            "checked\"")
        miss = replay.missing(snap, replay.required(snap, sh))
        assert [p for p, _ in miss] == [(replay.FP,)], (
            f"a snapshot with NO {replay.FP!r} branch at all was declared "
            f"complete: {len(miss)} are missing, and `books replay --check` "
            f"would have returned 0")
        assert not sh["verified"], (
            "the shape was not derived and the fingerprint was called "
            "CHECKED -- that word beside an underived shape was the chief lie")
        assert selfcheck(_tmp_out(tmp, snap)) > 0, (
            "the self-check returned zero on a snapshot with no fingerprint: "
            "a zero from not understanding passed off as a zero from a check")
    finally:
        replay.PKG = was
        _sh.rmtree(tmp, ignore_errors=True)


def test_derivable_shape_still_requires_every_value():
    """The other side: where the shape was derived, every value is required, or
    the requirement could be met by declaring any shape underivable."""
    tree = replay._parse(support.src_path("processing/layout/adapters/doclayout.py"))
    fn, cls = replay._fp_def(tree, "DocLayout")
    keys = replay._returned(fn, tree, cls)
    assert len(keys) > 10, (
        f"{len(keys)} values were derived from `DocLayout.fingerprint()` -- "
        f"the parse went blind and the requirement on the fingerprint "
        f"crumbled to one branch")
