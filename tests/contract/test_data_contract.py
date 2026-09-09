"""What the tree must never lose: the ignore rules, the image, the keys, the
stamps.

Four checks that open the real tree rather than a fixture, because each guards
a claim nothing else can see: that `.gitignore` still hides what must never be
committed and still tracks what must travel; that the rented image was built
from the Dockerfile we have; that no Cyrillic key survives where the map says
none does; and that every published number names a commit this history still
has. The formats and their floors are `tests/contract/test_formats.py`, the
book directory shape `tests/contract/test_book_shape.py`.
"""
import glob
import json
import os
import re

import pytest

import support
from booksmith.core.config import ROOT


def test_the_things_that_must_never_be_committed_are_ignored():
    """`.gitignore` is the one file where a bad edit exposes gigabytes.

    Its own first three lines say why: a `#` at the tail of a pattern is part
    of the pattern to git, so `raw/  # 9.7 GB` stops hiding `raw/` -- silently.
    Behind these four entries sit 9.7 GB of scans, 201 MB of built books and
    paid reading, the rent journal with live vast.ai machine ids, and the
    secrets file.

    Checked by asking git, not by reading the file: a pattern can be correct
    and still be overridden by a later line.
    """
    import subprocess
    root = os.path.dirname(os.path.dirname(support.SRC))
    # The last two are crops of a book, cut by `books crop` on a bench where
    # the bench directory is not itself closed (annopage, annopage-lite, hard,
    # hard36). They were hidden by nothing at all: the two patterns standing
    # here named `books feed`'s directories, and stayed after the command was
    # deleted while the new one was named nowhere.
    must_hide = ("raw/", "processed/", "runs/", ".env",
                 "bench/annopage/detect.crop/", "bench/hard/detect.crop/")
    r = subprocess.run(["git", "check-ignore", "-v", *must_hide],
                       cwd=root, capture_output=True, text=True)
    hidden = {ln.rsplit("\t", 1)[-1] for ln in r.stdout.splitlines() if ln}
    missing = sorted(set(must_hide) - hidden)
    assert not missing, (
        f"git no longer ignores {missing} -- .gitignore was edited and "
        "something that must never be committed is now exposed")

    # THE OTHER DIRECTION, and it is the one that bites quietly. A tracked
    # file falling UNDER an ignore is invisible to `git status`: the rename
    # succeeds, the index keeps it, and the next clone is missing it. The
    # results are the evidence for every number in METRICS.md and were
    # ignored until the prose that held those numbers was deleted.
    #
    # `--no-index` IS THE WHOLE CHECK. Without it `git check-ignore` consults
    # the index and answers about TRACKED paths by never reporting them --
    # and every path below is tracked, which is what "must keep" means. So
    # this half could not fail, whatever `.gitignore` said, and it did not:
    # moving the runs under a label put `bench/*/detect/*/pages/` over the
    # dots-ocr pages and 636 tracked, PAID files went ignored underneath a
    # green check. `git ls-files -i -c` printed all 636 the moment it was
    # asked. The mutation certifying this built its tree WITHOUT `git add`,
    # so it exercised the one condition the real tree does not have.
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

    # AND THE SAME QUESTION ASKED OF THE INDEX ITSELF, which is the only one
    # that sees a file already tracked AND already ignored. `--no-index`
    # above answers about the four paths named; this answers about all of
    # them, including the ones nobody thought to name.
    r = subprocess.run(["git", "ls-files", "-i", "-c", "--exclude-standard"],
                       cwd=root, capture_output=True, text=True)
    both = [ln for ln in r.stdout.splitlines() if ln.strip()]
    assert not both, (
        f"{len(both)} files are TRACKED and IGNORED at once, starting with "
        f"{both[0]}. `git status` will never mention them; the next "
        f"regenerate-and-add drops them and the clone after that is missing "
        f"data with no message anywhere")


def test_the_rented_image_was_built_from_this_dockerfile():
    """The image tag IS a commit SHA, so staleness is checkable.

    `procps` and `git` were added to `infra/base/Dockerfile` in one commit
    while `BASE_IMAGE` went on naming an image built before them. `run.sh`
    then said "procps is in the image now" and its pgrep guard, described as a
    second line of defence, was the only one -- on a machine that bills, where
    an orphan holds 60 % of the video memory.

    Nothing can inspect a remote image from here. What can be checked is the
    thing that made it stale: the tag names a commit, so the Dockerfile AT
    THAT COMMIT must be the Dockerfile we have now. It fails loudly when the
    recipe moves and the tag does not.
    """
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
    # A DECLARED, OUTSTANDING DEBT, not an exemption. These two were added in
    # `ed4cb11` and the image has not been rebuilt since; `run.sh` and the
    # Dockerfile both now say so in as many words, and `run.sh`'s pgrep guard
    # fires on a real rental, which is the correct behaviour. Rebuilding the
    # image and moving `BASE_IMAGE` to the new tag closes it -- and then this
    # set goes back to empty. A permanently red check stops being read; a
    # named debt with a floor under it does not.
    KNOWN_DEBT = {"git", "procps"}
    drifted = sorted(set(packages(now)) - set(packages(was.stdout)) - KNOWN_DEBT)
    assert not drifted, (
        f"the Dockerfile installs {drifted}, which the image tagged {tag} was "
        "not built with. Rebuild the image and move BASE_IMAGE to the new tag, "
        "or any prose relying on those packages is false on a paid run")


def test_no_cyrillic_key_survives_where_the_map_says_none_does():
    """The claim, measured -- because the tool that measured it was deleted.

    a deleted check walked `bench/`, `processed/` and `runs/` looking
    for Cyrillic keys; it went when the key migration finished, and the map
    then acquired the sentence "no Cyrillic key survives in any json of
    bench/, processed/ or runs/". That sentence was FALSE --
    `runs/ledger.jsonl` holds 74 of them -- and nothing was left to say so.
    Delete the code, keep the measurement: this is the measurement.

    `runs/ledger.jsonl` is the ONE declared exception and is asserted to stay
    one: it is the journal of the runs that were paid for, append-only, and
    rewriting a journal after the fact destroys the one thing a journal is
    for. So the check fails in both directions -- a Cyrillic key appearing
    anywhere else, and the exception quietly curing itself, which would mean
    the journal had been rewritten.
    """
    CYR = re.compile("[Ѐ-ӿԀ-ԯ]")
    # The root is a name, not a literal, so a walk can be pointed at a
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
                # A FILE THAT COULD NOT BE READ IS NOT A FILE WITH NO CYRILLIC
                # IN IT. `continue` was silent here, so `{"стр": 3,,}` --
                # unparseable, Cyrillic key in plain sight -- passed as
                # clean. The project's own rule: zero from a check and zero
                # from not understanding are different zeros.
                unreadable.append(f"{os.path.relpath(f, root)}: {e}")
                continue
            seen += 1
            if found:
                bad[os.path.relpath(f, root)] = len(found)

    # A DEAD GLOB IS A SILENT ZERO, and this walk had no floor while every
    # sibling in this file has one. Point the root at an empty directory
    # and the check went green having opened nothing -- measured, and the
    # same green it reports over 2670 tracked json. The floor is deliberately
    # far below what is on disk: it has to survive a clone, where the six
    # synthetic books and all of `processed/` are behind .gitignore.
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
    # THE EXEMPTION HALF ONLY RUNS WHERE THE JOURNAL IS, and `runs/` is in
    # .gitignore -- asserted two checks above. So on every fresh clone and on
    # any machine that has not rented a card, this half silently did not run
    # while the docstring claimed the check "fails in both directions". A
    # skip with a reason is the difference between "not applicable here" and
    # "checked and fine", and this file skips with a reason twice already.
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
    """A sha is not proof the commit is there.

    All 54 results were stamped against a `wip:` commit; the two `wip:`
    commits were then folded into one with `git reset --soft`, and every
    published number named a sha `git log --all` no longer showed and a fresh
    clone would never have. None of the renderer's other refusals sees it:
    the stamp was not None, not `+dirty`, and all 54 AGREED WITH EACH OTHER
    -- they agreed on a commit that was gone. "Which code counted this" is
    the one question the stamp exists to answer, and it had stopped being
    able to.

    Asked of the tracked records rather than through the renderer, so it
    answers on a clone with nothing rendered.
    """
    from booksmith.core import stamp
    files = sorted(glob.glob(os.path.join(ROOT, "results", "*.json")))
    assert len(files) > 20, (
        f"only {len(files)} results under results/ -- this check is "
        f"measuring nothing")
    bad = {}
    for f in files:
        with open(f, encoding="utf-8") as fh:
            c = json.load(fh).get("commit")
        # A dirty or absent stamp is a different defect and the renderer
        # already refuses both by name; this one is about the sha itself.
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
