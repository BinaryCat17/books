"""Three quantities without which a run does not repeat: file hash, commit,
packages.

APART, BECAUSE THE SNAPSHOT NOW HAS THREE WRITERS: `detect.py`, `doc/html.py`,
`read/run.py`. With one writer these were lawfully its own; with three, a
second copy is drift -- paid for once by the knob registry against the task
builder, 13 names of 17, and `dots_ocr/entrypoint.py` still admits "nothing
guards these two copies".

ANOTHER JUSTIFICATION STOOD HERE AND DOES NOT REPRODUCE: that `detect.py`
"will not come up at all" on a rented machine, wanting onnxruntime and opencv.
Both halves are false -- `import booksmith.detect` passes with `onnxruntime`,
`cv2` and `yaml` blocked, because they are pulled LAZILY inside functions of
`models/doclayout.py`, and on the machine they do exist, pinned by name in
`models/paddleocr_vl/constraints.txt`. One argument is left, and it is
checkable: three writers.

WHAT IS STILL NOT HERE. A third `_commit` lives in `synth.py` and says it in
OTHER words -- "(dirty tree)" in brackets against "+dirty tree" here, and
`'not a repository'` instead of `None` -- so the snapshots of `books synth`
and `books detect` about one tree already read differently. And `def _sha256`
occurs nine times in the tree. Merging that is work, not a line, and it is not
done; said here so it does not count as done.
"""
import hashlib
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


def commit() -> str | None:
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
    from . import knobs
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
        # The mark is the very string `detect._commit` wrote. One character
        # apart and the snapshots of two commands stop being comparable by
        # eye -- and by eye is exactly how they get compared.
        return head + ("+dirty tree" if d.stdout.strip() else "")
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
