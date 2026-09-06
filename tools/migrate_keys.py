"""Rename format keys across the data on disk, provably or not at all.

THE PROBLEM WITH REWRITING 6037 FILES. Of them, 3102 cannot be regenerated:
1272 dots pages counted on a rented GPU for $0.89, 891 answer files read for
$0.545, and the benches `annopage-lite` and `hard36`, whose builder is in
neither the tree nor the git history. A migration that reformats those, or
loses a key in them, is not a bug that can be fixed by re-running anything.

HOW THIS TOOL AVOIDS GUESSING. It never assumes a serialisation style. For
every file it first proves it can reproduce the ORIGINAL BYTES: parse, re-dump
under each candidate style, compare to the bytes on disk. Only a file that
round-trips exactly is eligible to be rewritten; anything else is reported and
left alone. So the failure mode is "this file was not migrated", printed, and
never "this file was migrated into a shape nobody expected".

Measured over all 6037: two styles cover every file.

    compact   json.dumps(o, ensure_ascii=False)                   3591 files
    indent1   json.dumps(o, ensure_ascii=False, indent=1)          2442
    compact\\n compact with a trailing newline                        3
    jsonl     one compact object per line, newline after each         1

WHAT IS NOT TOUCHED, AND WHY

  runs/ledger.jsonl   The rent journal, append-only. Its 74 Cyrillic keys are
                      not a contract -- `remote/ledger.py` never reads inside
                      `extra`, which is filled wholesale by `_run_facts()`.
                      Rewriting a journal after the fact destroys the one thing
                      a journal is for. New lines will arrive in English on
                      their own once the snapshot is English.
  the `сырое` subtree The model's answer, verbatim, with the vendor's own
                      `model`, `role`, `refusal`. "Распознанное неприкосновенно."
  processed/*/book.html and swaps.json
                      Not JSON key renames at all: `swaps.json` holds the
                      removed fragment verbatim plus two sha256 over it, so
                      rewriting the markup would mean forging the journal.
                      Those books are REBUILT from `assets/source/` instead,
                      after the code side of the rename -- see step 5.

    python3 tools/migrate_keys.py --dry      report what would change
    python3 tools/migrate_keys.py --apply    rewrite (after a backup)

THERE IS NO REVERSE PASS, AND THERE MUST NOT BE. It was written, run, and
withdrawn. Applying the map backwards is not the inverse of applying it
forwards, for two reasons, both measured:

  Nineteen English names in the map ALREADY existed as ASCII keys in the data
  before the migration -- `box` 63 785 times, `block_id`, `label`, `score`,
  `order`, `kind` 61 783 each, `model` 19 052, `role` 18 935, `width` and
  `height` 4782, and so on to 426 126 occurrences, 20.6 % of every key on
  disk. Whether a given `box` was `рамка` yesterday is not recoverable from
  the file; the map merges, and a merge has no inverse.

  The no-go zone is written as the literal `сырое`, so on the way back -- when
  the key is already `raw_answer` -- the guard does not fire. A reverse run in
  a sandbox put `модель` and `роль` inside the model's verbatim answer, and
  turned the vendor's own label dictionary (`text`, `table`, `number` of
  PP-DocLayoutV2) into Russian. That is the rule "распознанное неприкосновенно"
  broken by the tool that carries the rule in its own docstring.

The way back is the backup, and the way to a better one would be a per-file
journal written during `--apply` (which key, in which object, became what) --
not a symmetric map.
"""
import collections
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAP = os.path.join(ROOT, "tools", "keymap.json")
VALUES = os.path.join(ROOT, "tools", "valuemap.json")
NO_GO = "сырое"
SKIP_FILES = ("runs/ledger.jsonl",)

STYLES = ("compact", "indent1", "compact_nl")


def dumps(doc, style):
    if style == "indent1":
        return json.dumps(doc, ensure_ascii=False, indent=1).encode("utf-8")
    body = json.dumps(doc, ensure_ascii=False).encode("utf-8")
    return body + b"\n" if style == "compact_nl" else body


def sniff(raw, doc):
    """The style that reproduces these exact bytes, or None. No guessing."""
    for style in STYLES:
        try:
            if dumps(doc, style) == raw:
                return style
        except (TypeError, ValueError):
            return None
    return None


def data_files():
    out = []
    for base in ("bench", "processed", "runs"):
        for dp, _, fn in os.walk(os.path.join(ROOT, base)):
            for f in fn:
                if f.endswith((".json", ".jsonl")):
                    rel = os.path.relpath(os.path.join(dp, f), ROOT)
                    if rel not in SKIP_FILES:
                        out.append(rel)
    return sorted(out)


def rename(obj, keymap, valuemap, under_no_go=False):
    """A copy with keys renamed, and enumerated values renamed under their key.

    Key order is preserved: dicts keep insertion order, and every writer in
    this project builds them in one pass, so the rewritten file differs from
    the original only in the names.

    VALUES ARE SCOPED BY THEIR KEY, and that scoping is the whole safety of
    the value side. The word `текст` is a policy class when it is the value of
    `роль` (20 140 times) and a fragment of a Russian book when it is the value
    of `текст` (9760 times, 3149 of them distinct). A flat value map would
    translate the books.
    """
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            new = k if under_no_go else keymap.get(k, k)
            if not under_no_go and k in valuemap:
                v = _map_value(v, valuemap[k])
            out[new] = rename(v, keymap, valuemap, under_no_go or k == NO_GO)
        return out
    if isinstance(obj, list):
        return [rename(v, keymap, valuemap, under_no_go) for v in obj]
    return obj


def _map_value(v, table):
    """One value, or a list of them. Anything else is passed through."""
    if isinstance(v, str):
        return table.get(v, v)
    if isinstance(v, list):
        return [table.get(x, x) if isinstance(x, str) else x for x in v]
    return v


def process(rel, keymap, valuemap, apply_it):
    """(style, renamed_count, error). Never writes unless the file round-trips."""
    path = os.path.join(ROOT, rel)
    raw = open(path, "rb").read()
    try:
        doc = json.loads(raw)
    except ValueError as e:
        return None, 0, f"not JSON: {e}"
    style = sniff(raw, doc)
    if style is None:
        return None, 0, "style not reproducible -- refusing to rewrite"
    before = collections.Counter()
    _count_keys(doc, before)
    new_doc = rename(doc, keymap, valuemap)
    after = collections.Counter()
    _count_keys(new_doc, after)
    changed = sum(v for k, v in before.items() if k in keymap)
    if not changed and _values_differ(doc, new_doc):
        changed = 1                      # a value-only rewrite still counts
    if sum(before.values()) != sum(after.values()):
        return style, 0, (f"key count changed {sum(before.values())} -> "
                          f"{sum(after.values())}: a rename collided")
    if apply_it and changed:
        with open(path, "wb") as f:
            f.write(dumps(new_doc, style))
    return style, changed, None


def _values_differ(a, b):
    return json.dumps(a, ensure_ascii=False, sort_keys=True) != \
        json.dumps(b, ensure_ascii=False, sort_keys=True)


def _count_keys(obj, counter):
    if isinstance(obj, dict):
        for k, v in obj.items():
            counter[k] += 1
            _count_keys(v, counter)
    elif isinstance(obj, list):
        for v in obj:
            _count_keys(v, counter)


def main(argv):
    if not os.path.isfile(MAP):
        print(f"no key map at {MAP}")
        return 1
    keymap = json.load(open(MAP, encoding="utf-8"))
    valuemap = json.load(open(VALUES, encoding="utf-8"))["by_key"]
    if "--back" in argv:
        print("--back was removed: the map merges 19 names that already "
              "existed in ASCII (426 126 keys, 20.6 % of the data), and the "
              "no-go zone does not hold on the way back. Restore the backup.")
        return 1
    apply_it = "--apply" in argv
    files = data_files()
    styles = collections.Counter()
    errors, touched, renamed = [], 0, 0
    for rel in files:
        style, n, err = process(rel, keymap, valuemap, apply_it)
        styles[style or "UNREPRODUCIBLE"] += 1
        if err:
            errors.append((rel, err))
        if n:
            touched += 1
            renamed += n
    print("styles:")
    for s, n in styles.most_common():
        print(f"  {n:>6}  {s}")
    print(f"\nfiles seen {len(files)}, files with renamed keys {touched}, "
          f"keys renamed {renamed}")
    if errors:
        print(f"\nREFUSED {len(errors)} files:")
        for rel, err in errors[:20]:
            print(f"  {rel}: {err}")
    if not apply_it:
        print("\n(dry run -- nothing written)")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
