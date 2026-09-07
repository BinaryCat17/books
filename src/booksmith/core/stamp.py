"""Four quantities without which a run does not repeat: file hash, commit,
packages, and the identity of the experiment itself.

APART, BECAUSE THE SNAPSHOT NOW HAS THREE WRITERS: `layout/detect.py`,
`assemble/html.py`, `read/driver.py`. With one writer these were lawfully
their own; with three, a
second copy is drift -- paid for once by the knob registry against the task
builder, 13 names of 17, and `dots_ocr/entrypoint.py` still admits "nothing
guards these two copies".

ANOTHER JUSTIFICATION STOOD HERE AND DOES NOT REPRODUCE: that `detect.py`
"will not come up at all" on a rented machine, wanting onnxruntime and opencv.
Both halves are false -- `import booksmith.detect` passes with `onnxruntime`,
`cv2` and `yaml` blocked, because they are pulled LAZILY inside functions of
`layout/adapters/doclayout.py`, and on the machine they do exist, pinned by
name in `read/rented/paddleocr_vl/constraints.txt`. One argument is left,
and it is
checkable: three writers.

WHAT USED TO STAND HERE, and was done on 2026-09-07 with the package move:
a third `_commit` in `synth.py` that said "(dirty tree)" in brackets where
this file says "+dirty tree", and `"not a repository"` where this file says
`None`; and `def _sha256` nine times in the tree. The synthetic manifests
tracked in `bench/` were rebuilt the same day and carry the shared marker;
the seven file hashers are gone and `apply._sha256` (over TEXT) and
`replay._sha256` (`None` on OSError, a value the check branches on) stay
because they are not copies.
"""
import hashlib
import json
import os
import subprocess
import sys

# Packages that decide PAGE PARSING. Declared by the caller, not baked in:
# detection and reading need different ones, and a shared list would silently
# write `null` against a package this run never wanted -- "we did not look"
# passed off as "absent".
DETECT_PACKAGES = ("onnxruntime", "numpy", "cv2", "pymupdf", "yaml")
READ_PACKAGES = ("pymupdf",)


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# What a measuring pass WRITES, and therefore may not be judged dirty by. Not
# a general escape: every entry is an output of this project, never a source,
# and `tests/test_data_contract.py` holds the list to that.
OUTPUT_PATHS = ("results/", "METRICS.md")


def commit(ignore: tuple[str, ...] = ()) -> str | None:
    """The commit of the code that counted. A dirty tree is marked EXPLICITLY.

    Marked, not passed over: a run on uncommitted edits cannot be repeated,
    and that must be known while the snapshot is being read, not later.

    git is asked IN THE SOURCE DIRECTORY, not in the process's working one:
    the command can be called from anywhere -- a foreign repository, a
    directory with no git at all -- and the snapshot would record a foreign
    commit, or `None` beside a live repository. Both troubles are silent.
    """
    # The root is taken FROM THE PACKAGE, not by four `dirname` off this file.
    # Not cosmetic: the first edition took three (as `detect.py` did, whence
    # this rule moved) and got `src/` instead of the root -- git then answered
    # for the enclosing repository. Counting levels breaks at the first move
    # of the file; `booksmith.__file__` knows where the package is by itself.
    #
    # WHAT THIS DOES NOT CATCH, and silence is forbidden: a package lying
    # INSIDE a foreign repository hands back a foreign commit. Checked: a flat
    # layout inside someone else's git gives its HEAD. Nothing tells "our
    # repository" from "some repository" -- short of comparing paths, and the
    # package lawfully lives installed as well. On the box this is safe by
    # accident: it lands in `$WORK/booksmith`, there is no git there at all,
    # and the answer is `None`.
    import booksmith
    # WHAT IS TOLD FROM OUTSIDE COUNTS ONLY WHERE GIT IS SILENT. A rented
    # machine has no git at all (checked by unpacking the image layers), and
    # the run there is the only paid one -- it must not be left without a
    # record of the code. The task builder puts its own `commit()` here; the
    # order is exactly this -- local git, when there is any, is the truer one.
    from booksmith.core import knobs
    told = knobs.knob("BOOKSMITH_COMMIT")
    root = os.path.dirname(os.path.dirname(
        os.path.abspath(booksmith.__file__)))
    try:
        h = subprocess.run(["git", "-C", root, "rev-parse", "HEAD"],
                           capture_output=True, text=True, timeout=10)
        if h.returncode != 0:
            return told or None
        head = h.stdout.strip()
        d = subprocess.run(["git", "-C", root, "status", "--porcelain"],
                           capture_output=True, text=True, timeout=10)
        lines = [ln for ln in d.stdout.splitlines() if ln.strip()]
        if ignore:
            # THE OUTPUT MAY NOT INVALIDATE ITS OWN PROVENANCE. The stamp
            # answers "which code counted this", and a file the run is
            # WRITING is not code. `results/*.json` became tracked when
            # METRICS.md started being rendered from them, and the moment it
            # did, a measuring pass dirtied the tree with its own first
            # result and stamped every later one `+dirty` -- so a result
            # could never be stamped cleanly again and the renderer refused
            # all of them forever. The caller names what it is writing; it
            # cannot name `src/`.
            lines = [ln for ln in lines
                     if not any(ln[3:].strip().strip('"').startswith(p)
                                for p in ignore)]
        # The mark is the very string `detect._commit` wrote. One character
        # apart and the snapshots of two commands stop being comparable by
        # eye -- and by eye is exactly how they get compared.
        return head + ("+dirty tree" if lines else "")
    except (OSError, subprocess.SubprocessError):
        return told or None


def packages(names=DETECT_PACKAGES) -> dict:
    out = {}
    for name in names:
        try:
            out[name] = __import__(name).__version__
        except Exception:                      # noqa: BLE001
            out[name] = None                   # a value, not a gap
    out["python"] = sys.version.split()[0]
    return out


# ---------------------------------------------------------------- identity
# WHAT IDENTITY IS FOR. A run lives under a label -- the model's name -- and
# two runs of the SAME model can still be two different experiments: another
# threshold, another pipeline, another seed. `identity` is the sha256 that
# tells them apart, so a command about to write into an existing label can
# refuse instead of merging one experiment into another's directory.
#
# THE EXCLUSIONS ARE THE WHOLE DESIGN, and the first list was wrong in both
# directions. Two rules:
#
#   Anything that moves WITHOUT the experiment moving must be out, or two runs
#   of one experiment get two identities and a legitimate second run is
#   refused. This is the dangerous direction, because the refusal looks like
#   the guard working.
#
#   Anything the experiment moves with must be IN, or two different
#   experiments share an identity and the second silently resumes the first.
#
# WHAT IS NOT EXCLUDED, though an earlier draft argued about both. `providers`
# is machine-local in principle and constant here (all three adapters build
# the session with `["CPUExecutionProvider"]`), and CPU against CUDA really
# would be two experiments -- so it stays. `sha256_command` is not in a
# fingerprint at all: it lives beside it, in the snapshot's `adapter` block,
# and it is the hash of the driver's source, which moves on a comment.
# Folding it in would move every identity on a prose edit.
FINGERPRINT_NOT_IDENTITY = {
    "weights_dir": "a machine-local path; the weights themselves are in "
                   "sha256_weights, which IS the experiment",
    "summary": "run-born: docling writes its pipeline totals into the "
               "fingerprint AFTER the pages, so it exists only once the run "
               "is over -- and it is NESTED, under `docling_pipeline`, which "
               "is why the exclusion goes to every depth",
    "dir": "a machine-local path to the weights, wherever it appears. The "
           "reading adapter's `weights` block opens with `VL_MODEL_DIR`, so "
           "excluding that knob and admitting the same fact one field over "
           "was no exclusion at all: two readings of one book on two rented "
           "cards got two identities",
    "file_count": "how many files that directory happened to hold; it moves "
                  "with the download, not with the model",
}

# Knobs whose value moves without the experiment moving. `VLM_ENDPOINT` is the
# rented box's host:port and is NEW ON EVERY RENTAL -- with it in, a second
# reading of the same book with the same model on a fresh card would be
# refused as a different experiment, which is the failure mode this whole
# guard must not have. The two weights directories are the knob half of
# `weights_dir` above: excluding the path from the fingerprint and admitting
# the same fact through a knob would be no exclusion at all.
KNOBS_NOT_IDENTITY = {
    "VLM_ENDPOINT": "the rented machine's address, new on every rental",
    "LAYOUT_MODEL_DIR": "a machine-local path to the weights",
    "VL_MODEL_DIR": "a machine-local path to the weights",
    "BOOKSMITH_LEDGER": "where the run journal is written",
    "BOOKSMITH_COMMIT": "how the commit is discovered on a box without git",
}


def _without(obj, names):
    """The mapping with `names` dropped AT EVERY DEPTH.

    Top-level only was the first edition, and docling proved it wrong: its
    fingerprint nests the vendor pipeline's own under `docling_pipeline`, and
    THAT holds the pipeline's accumulating page counters under `summary` --
    `page_count`, `boxes_before`, `boxes_after`. So with `DOCLING_PIPELINE=
    post|full` the identity became a function of HOW MANY PAGES the run
    covered: not an experiment key at all, and the second run of an identical
    experiment refused forever under a message saying it was a different one.
    That is the direction this module warns about, where the refusal looks
    like the guard working.

    Invisible on disk today only because every run in the tree is
    `DOCLING_PIPELINE=off`, where the nest is `null`.
    """
    if isinstance(obj, dict):
        return {k: _without(v, names) for k, v in obj.items()
                if k not in names}
    if isinstance(obj, list):
        return [_without(v, names) for v in obj]
    return obj


def identity(fingerprint: dict, knob_values: dict) -> str:
    """sha256 over what makes this run THIS experiment.

    VALUES ONLY, never the registry entries. A knob's snapshot entry carries
    `what` -- prose this project edits constantly -- and `set_externally`,
    which differs between a knob set to `0.5` in `.env` and the same knob left
    at its default `0.5`. Hashing either would give one experiment two
    identities, and the refusal would look like the guard working.
    """
    keep_f = _without(fingerprint or {}, FINGERPRINT_NOT_IDENTITY)
    keep_k = {k: v for k, v in (knob_values or {}).items()
              if k not in KNOBS_NOT_IDENTITY}
    blob = json.dumps({"fingerprint": keep_f, "knobs": keep_k},
                      sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def knob_values(snapshot: dict) -> dict:
    """The value of each knob THIS RUN ACTUALLY READ, out of a snapshot.

    The snapshot shape is `knobs/<NAME>/value`, one shape everywhere, and
    this is the one reader that turns it back into the plain mapping
    `identity` wants.

    `for_this_run` IS THE WHOLE POINT. The block is complete -- every knob of
    the registry, because a partial snapshot is not repeatable -- and each
    entry says who reads it, `for_this_run: false` when nobody does. Hashing
    the complete block would make `HTML_MATH` part of a DETECTION run's
    identity, and a change to how formulas are drawn would refuse the next
    detect run as a different experiment. That is the direction that must not
    be wrong: the refusal would look like the guard working.
    """
    out = {}
    for name, entry in ((snapshot or {}).get("knobs") or {}).items():
        if not isinstance(entry, dict):
            out[name] = entry
        elif entry.get("for_this_run"):
            out[name] = entry.get("value")
    return out
