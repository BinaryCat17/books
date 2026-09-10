"""What the tree must never lose: the ignore rules, the image, the keys, the
stamps.

Four checks over the real tree rather than a fixture: that `.gitignore` still
hides what must never be committed and still tracks what must travel; that the
rented image was built from the Dockerfile we have; that no Cyrillic key
survives where the map says none does; and that every published number names a
commit this history still has. Formats and their floors are
`tests/contract/test_formats.py`, the book shape `tests/contract/test_book_shape.py`.
"""
import glob
import json
import os
import re

import pytest

import support
from booksmith.core.config import ROOT


def test_the_things_that_must_never_be_committed_are_ignored():
    """`.gitignore` is the one file where a bad edit exposes gigabytes: a `#` at
    the tail of a pattern is part of the pattern to git. Asked of git, not of
    the file, since a pattern can be correct and overridden by a later line."""
    import subprocess
    root = os.path.dirname(os.path.dirname(support.SRC))
    # The last two are the crop directories of a bench that is not itself
    # closed (annopage, annopage-lite, hard, hard36).
    must_hide = ("raw/", "processed/", "runs/", ".env",
                 "bench/annopage/detect.crop/", "bench/hard/detect.crop/")
    r = subprocess.run(["git", "check-ignore", "-v", *must_hide],
                       cwd=root, capture_output=True, text=True)
    hidden = {ln.rsplit("\t", 1)[-1] for ln in r.stdout.splitlines() if ln}
    missing = sorted(set(must_hide) - hidden)
    assert not missing, (
        f"git no longer ignores {missing} -- .gitignore was edited and "
        "something that must never be committed is now exposed")

    # The other direction: a tracked file falling under an ignore is invisible
    # to `git status`, so the next clone is missing it.
    # `--no-index` is the whole check -- with the index consulted, a tracked
    # path is never reported and this half could not fail.
    must_keep = ("results/slovar-PP-DocLayoutV2.json",
                 "docs/commands.md",
                 "bench/annopage/detect/PP-DocLayoutV2/run.json",
                 "bench/annopage/truth/0001.json")
    r = subprocess.run(["git", "check-ignore", "--no-index", *must_keep],
                       cwd=root, capture_output=True, text=True)
    hidden = [ln for ln in r.stdout.splitlines() if ln.strip()]
    assert not hidden, (
        f"git now IGNORES {hidden}, and these must travel with the tree: a "
        f"result is the evidence for a published number, and a snapshot says "
        f"which knobs produced one")

    # The same question asked of the index itself, the only one that sees a
    # file already tracked and already ignored, named here or not.
    r = subprocess.run(["git", "ls-files", "-i", "-c", "--exclude-standard"],
                       cwd=root, capture_output=True, text=True)
    both = [ln for ln in r.stdout.splitlines() if ln.strip()]
    assert not both, (
        f"{len(both)} files are TRACKED and IGNORED at once, starting with "
        f"{both[0]}. `git status` will never mention them; the next "
        f"regenerate-and-add drops them and the clone after that is missing "
        f"data with no message anywhere")


def test_the_rented_image_was_built_from_this_dockerfile():
    """The image tag is a commit SHA, so staleness is checkable: nothing can
    inspect a remote image from here, but the Dockerfile at that commit must be
    the Dockerfile we have now."""
    import subprocess
    root = os.path.dirname(os.path.dirname(support.SRC))
    src = open(os.path.join(support.SRC, "remote", "image.py"),
               encoding="utf-8").read()
    m = re.search(r'BASE_IMAGE\s*=\s*"[^"]*:([0-9a-f]{7,40})"', src)
    assert m, "BASE_IMAGE no longer carries a commit SHA as its tag"
    tag = m.group(1)
    was = subprocess.run(["git", "show", f"{tag}:infra/base/Dockerfile"],
                         cwd=root, capture_output=True, text=True)
    if was.returncode:
        pytest.skip(f"commit {tag} is not in this clone -- nothing to compare")
    now = open(os.path.join(root, "infra", "base", "Dockerfile"),
               encoding="utf-8").read()

    def packages(text):
        block = text.split("apt-get install", 1)[-1].split("rm -rf", 1)[0]
        return sorted(w for w in re.findall(r"^\s+([a-z0-9.+-]+)\s*\\?$",
                                            block, re.M))
    # A declared, outstanding debt, not an exemption: the image has not been
    # rebuilt since these two were added, and moving `BASE_IMAGE` to a new tag
    # empties this set.
    KNOWN_DEBT = {"git", "procps"}
    drifted = sorted(set(packages(now)) - set(packages(was.stdout)) - KNOWN_DEBT)
    assert not drifted, (
        f"the Dockerfile installs {drifted}, which the image tagged {tag} was "
        "not built with. Rebuild the image and move BASE_IMAGE to the new tag, "
        "or any prose relying on those packages is false on a paid run")


def test_no_cyrillic_key_survives_where_the_map_says_none_does():
    """No Cyrillic key in any json of `bench/`, `processed/` or `runs/`, with one
    exception: `runs/ledger.jsonl`, the append-only journal of the paid runs.
    The check fails both ways, the exception curing itself included."""
    CYR = re.compile("[Ѐ-ӿԀ-ԯ]")
    # The root is a name, not a literal, so the walk can be pointed at a
    # doctored tree and watched going red.
    root = ROOT

    def keys(o, out):
        if isinstance(o, dict):
            for k, v in o.items():
                if CYR.search(str(k)):
                    out.add(k)
                keys(v, out)
        elif isinstance(o, list):
            for v in o:
                keys(v, out)

    bad, seen, unreadable = {}, 0, []
    for pat in ("bench/**/*.json", "processed/**/*.json", "runs/*.jsonl"):
        for f in glob.glob(os.path.join(root, pat), recursive=True):
            found = set()
            try:
                with open(f, encoding="utf-8") as fh:
                    if f.endswith(".jsonl"):
                        for line in fh:
                            if line.strip():
                                keys(json.loads(line), found)
                    else:
                        keys(json.load(fh), found)
            except (OSError, ValueError) as e:
                # A file that could not be read is not a file with no Cyrillic
                # in it: zero from a check and zero from not understanding are
                # different zeros.
                unreadable.append(f"{os.path.relpath(f, root)}: {e}")
                continue
            seen += 1
            if found:
                bad[os.path.relpath(f, root)] = len(found)

    # A dead glob is a silent zero, so the walk has a floor -- far below what
    # is on disk, since it must survive a clone where most of it is ignored.
    assert seen > 700, (
        f"only {seen} json were read under {root} -- this check is measuring "
        f"nothing. Either the three globs stopped matching or the tree is not "
        f"where the root points.")
    assert not unreadable, (
        f"{len(unreadable)} tracked json could not be parsed, so nothing is "
        f"known about the keys in them: {unreadable[:3]}")

    LEDGER = os.path.join("runs", "ledger.jsonl")
    others = {k: v for k, v in bad.items() if k != LEDGER}
    assert not others, (
        f"Cyrillic keys where the map says there are none: {others}. The key "
        f"migration is finished and its tools are deleted; a key in Russian "
        f"here means data written by code that predates it, or a rename that "
        f"went backwards.")
    # The exemption half only runs where the journal is, and `runs/` is
    # gitignored: a skip with a reason, not a silent pass.
    if not os.path.isfile(os.path.join(root, LEDGER)):
        pytest.skip(
            f"{LEDGER} is not here -- `runs/` is gitignored, so the "
            f"append-only half of this check has nothing to ask")
    assert bad.get(LEDGER), (
        f"{LEDGER} no longer holds a Cyrillic key. It is the journal of "
        f"the runs that were PAID FOR and is append-only -- if its old "
        f"lines are English now, the journal was rewritten after the "
        f"fact, which destroys the one thing a journal is for. If it was "
        f"rewritten on purpose, delete this half of the check and the "
        f"exception in CLAUDE.md with it.")


def test_every_result_names_a_commit_this_history_still_has():
    """A sha is not proof the commit is there: results can agree with each other
    on a commit a rewritten history no longer has. Asked of the tracked records
    rather than through the renderer, so it answers on a clone as well."""
    from booksmith.core import stamp
    files = sorted(glob.glob(os.path.join(ROOT, "results", "*.json")))
    assert len(files) > 20, (
        f"only {len(files)} results under results/ -- this check is "
        f"measuring nothing")
    bad = {}
    for f in files:
        with open(f, encoding="utf-8") as fh:
            c = json.load(fh).get("commit")
        # A dirty or absent stamp is a different defect the renderer refuses
        # by name; this one is about the sha itself.
        if not c or "dirty" in c:
            continue
        if stamp.reachable(c) is not True:
            bad.setdefault(c, []).append(os.path.basename(f))
    assert not bad, (
        "results name commits that are not in this history: "
        + "; ".join(f"{c} ({len(v)} files)" for c, v in bad.items())
        + ". History was rewritten under them -- a squash, a rebase, an "
          "amend -- so the code that produced these numbers cannot be got "
          "back. Re-measure: python3 tools/sweep.py --apply --metrics-only")
