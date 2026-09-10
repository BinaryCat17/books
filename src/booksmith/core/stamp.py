"""Four quantities without which a run does not repeat: file hash, commit,
packages, and the identity of the experiment itself.

Their own module because the snapshot has three writers -- `layout/detect.py`,
`assemble/html.py`, `read/driver.py` -- and a second copy of any of the four
drifts. `identity` is a sha256 that tells two runs of one model apart, so a
command about to write into an existing label can refuse instead of merging two
experiments. What moves without the experiment moving is excluded from it, or a
legitimate second run is refused; what the experiment moves with is included,
or the second silently resumes the first.
"""
from collections.abc import Iterable, Mapping
import hashlib
import json
import os
import subprocess
import sys

# Packages that decide page parsing, declared by the caller: detection and
# reading need different ones, and "we did not look" must not read as "absent".
DETECT_PACKAGES = ("onnxruntime", "numpy", "cv2", "pymupdf", "yaml")
READ_PACKAGES = ("pymupdf",)


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# What a measuring pass writes, and so may not be judged dirty by; outputs only.
OUTPUT_PATHS = ("results/", "METRICS.md")


def commit(ignore: tuple[str, ...] = ()) -> str | None:
    """The commit of the code that counted. A dirty tree is marked explicitly.

    git is asked in the source directory, not the process's working one, or the
    snapshot records a foreign commit, or `None` beside a live repository.
    """
    # The root comes from the package, not by counting `dirname` levels off this
    # file; a package inside a foreign repository yields that repository's commit.
    import booksmith
    # What is told from outside counts only where git is silent: a rented box has none.
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
            # The output may not invalidate its own provenance: a file the run
            # is writing is not code. The caller names it, and cannot name `src/`.
            lines = [ln for ln in lines
                     if not any(ln[3:].strip().strip('"').startswith(p)
                                for p in ignore)]
        # One mark for every writer, or two snapshots stop comparing by eye.
        return head + ("+dirty tree" if lines else "")
    except (OSError, subprocess.SubprocessError):
        return told or None


def reachable(sha: str) -> bool | None:
    """Is this commit an ancestor of HEAD -- does the code that counted still
    exist? Ancestor and not equal, so an older result stays traceable, and
    `None` where git cannot answer at all, which is not `False`.
    """
    if not sha:
        return None
    import booksmith
    root = os.path.dirname(os.path.dirname(
        os.path.abspath(booksmith.__file__)))
    try:
        r = subprocess.run(
            ["git", "-C", root, "merge-base", "--is-ancestor",
             sha.split("+")[0], "HEAD"],
            capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    # 0 ancestor, 1 not, anything else git failing to answer: "I cannot tell" is not "no".
    return True if r.returncode == 0 else (False if r.returncode == 1
                                           else None)


def packages(names: Iterable[str] = DETECT_PACKAGES) -> dict:
    out = {}
    for name in names:
        try:
            out[name] = __import__(name).__version__
        except Exception:
            out[name] = None                   # a value, not a gap
    out["python"] = sys.version.split()[0]
    return out


# ---------------------------------------------------------------- identity
# Fingerprint fields outside the identity, each carrying its reason as a value.
# `providers` stays in: CPU against CUDA would be two experiments.
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

# Knobs whose value moves without the experiment: an address, a local path, a journal.
KNOBS_NOT_IDENTITY = {
    "VLM_ENDPOINT": "the rented machine's address, new on every rental",
    "LAYOUT_ENDPOINT": "where a served layout model was reached; the model "
                       "itself is in the fingerprint",
    "LAYOUT_ADAPTER": "how the model was reached, in-process or served; what "
                      "answered is the fingerprint's name and weights, so a "
                      "served run of a model is the run of that model",
    "LAYOUT_MODEL_DIR": "a machine-local path to the weights",
    "VL_MODEL_DIR": "a machine-local path to the weights",
    "BOOKSMITH_LEDGER": "where the run journal is written",
    "BOOKSMITH_COMMIT": "how the commit is discovered on a box without git",
}


def _without(obj: object, names: Iterable[str]) -> object:
    """The mapping with `names` dropped at every depth.

    Every depth, because docling nests its pipeline's fingerprint under
    `docling_pipeline` and the run's page counters sit inside that nest.
    """
    if isinstance(obj, dict):
        return {k: _without(v, names) for k, v in obj.items()
                if k not in names}
    if isinstance(obj, list):
        return [_without(v, names) for v in obj]
    return obj


def identity(fingerprint: dict, knob_values: dict) -> str:
    """sha256 over what makes this run this experiment.

    Values only, never the registry entries: `what` is prose, and
    `set_externally` differs between a knob set to its default and left at it.
    """
    keep_f = _without(fingerprint or {}, FINGERPRINT_NOT_IDENTITY)
    keep_k = {k: v for k, v in (knob_values or {}).items()
              if k not in KNOBS_NOT_IDENTITY}
    blob = json.dumps({"fingerprint": keep_f, "knobs": keep_k},
                      sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def merge_knobs(server: Mapping, client: Mapping) -> dict:
    """The knobs read on both sides of a served model, as one mapping. A name
    read on both with two values is refused, not chosen: the run would then
    be an experiment nobody can name."""
    both = {k: (server[k], client[k]) for k in server
            if k in client and str(server[k]) != str(client[k])}
    if both:
        from booksmith.core.errors import Refusal
        raise Refusal(
            f"knobs read on both sides of the model with two values: "
            f"{ {k: list(v) for k, v in both.items()} }. One run cannot be "
            f"two experiments; set the value on one side only.")
    return {**(server or {}), **(client or {})}


def knob_values(snapshot: dict) -> dict:
    """The value of each knob this run actually read, out of `knobs/<NAME>/value`,
    and, for a served model, the values its own side read, out of `served/knobs`.

    Only the `for_this_run` entries: over the complete block `HTML_MATH` would
    join a detection run's identity and refuse the next detect run.
    """
    out = {}
    for name, entry in ((snapshot or {}).get("knobs") or {}).items():
        if not isinstance(entry, dict):
            out[name] = entry
        elif entry.get("for_this_run"):
            out[name] = entry.get("value")
    spoken = (snapshot or {}).get("served")
    if isinstance(spoken, dict) and isinstance(spoken.get("knobs"), dict):
        out = merge_knobs(spoken["knobs"], out)
    return out
