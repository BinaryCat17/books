"""Is the key map safe to apply? Five ways it could quietly destroy data.

The map renames 562 format names at once, across 6037 files, of which 3102
cannot be regenerated -- 1272 counted on a rented GPU for $0.89, 891 read for
$0.545, and two benches whose builder exists neither in the tree nor in git
history. There is no undo for those beyond the backup, so the map is checked
before it is applied, not after.

WHAT IS CHECKED, AND WHY EACH ONE

1. TOTALITY. Every name in the inventory must be in the map. A name left out
   is not an error at migration time -- it simply stays Russian, in a file
   whose other keys are English, and nothing says so.

2. INJECTIVITY. Two Russian keys mapping to one English name is a merge. Merges
   are sometimes right (`ширина` and an existing ASCII `width` are the same
   quantity) and sometimes fatal, so every one has to be declared rather than
   discovered.

3. SIBLING COLLISION -- the fatal case. Two keys that map to one name AND live
   in the same object destroy data: the second overwrites the first and the
   file stays valid JSON. Known instance: `страниц` (a number) and `страницы`
   (a list) sit side by side in seven `bench/*/manifest.json`. Checked against
   every object of every file, not against the map alone.

4. COLLISION WITH EXISTING ASCII. If a new English name already exists as an
   ASCII key in the same object, the same destruction happens without any two
   Russian keys being involved.

5. THE `сырое` NO-GO ZONE. Under that key lies the model's answer, verbatim,
   with the vendor's own ASCII `model`, `role`, `refusal`, `choices`. The
   project rule is that what was recognised is untouchable. Anything the map
   would rename inside that subtree is reported, and the migration must skip it.

    python3 tools/keymap_check.py            check tools/keymap.json
    python3 tools/keymap_check.py --quiet    only the verdict
"""
import collections
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAP = os.path.join(ROOT, "tools", "keymap.json")
NO_GO = "сырое"
SNAKE = re.compile(r"^[a-z][a-z0-9_]*$")


def cyrillic(s):
    return any("Ѐ" <= c <= "ӿ" for c in s)


def data_files():
    out = []
    for base in ("bench", "processed", "runs"):
        for dp, _, fn in os.walk(os.path.join(ROOT, base)):
            for f in fn:
                if f.endswith((".json", ".jsonl")):
                    out.append(os.path.join(dp, f))
    return sorted(out)


def _objects(obj, inside_no_go=False):
    """Every dict in the tree, with a flag: is it under `сырое`?"""
    if isinstance(obj, dict):
        yield obj, inside_no_go
        for k, v in obj.items():
            yield from _objects(v, inside_no_go or k == NO_GO)
    elif isinstance(obj, list):
        for v in obj:
            yield from _objects(v, inside_no_go)


def load_json(path):
    if path.endswith(".jsonl"):
        return [json.loads(ln) for ln in open(path, encoding="utf-8") if ln.strip()]
    return json.load(open(path, encoding="utf-8"))


def check(keymap, inventory):
    bad = collections.defaultdict(list)

    missing = [k for k in inventory if k not in keymap]
    if missing:
        bad["not in the map"] = sorted(missing)

    shape = [f"{k!r} -> {v!r}" for k, v in keymap.items()
             if not isinstance(v, str) or not SNAKE.match(v)]
    if shape:
        bad["not ascii snake_case"] = sorted(shape)

    back = collections.defaultdict(list)
    for k, v in keymap.items():
        back[v].append(k)
    merges = {v: sorted(ks) for v, ks in back.items() if len(ks) > 1}
    if merges:
        bad["two russian keys share one english name"] = [
            f"{v}: {', '.join(ks)}" for v, ks in sorted(merges.items())]

    siblings, ascii_hits, no_go = set(), set(), set()
    for path in data_files():
        rel = os.path.relpath(path, ROOT)
        try:
            doc = load_json(path)
        except (ValueError, OSError):
            continue
        for obj, under in _objects(doc):
            renamed = {}
            for k in obj:
                if under and cyrillic(k):
                    no_go.add(k)
                    continue
                new = keymap.get(k)
                if new is None:
                    continue
                if new in renamed:
                    siblings.add((renamed[new], k, new, rel))
                elif new in obj and new != k:
                    ascii_hits.add((k, new, rel))
                renamed[new] = k
    if siblings:
        bad["SAME OBJECT -- one would overwrite the other"] = sorted(
            f"{a!r} + {b!r} -> {new!r}   ({rel})" for a, b, new, rel in siblings)
    if ascii_hits:
        bad["new name already an ASCII key in the same object"] = sorted(
            f"{k!r} -> {new!r} collides   ({rel})" for k, new, rel in ascii_hits)
    if no_go:
        bad[f"cyrillic keys under {NO_GO!r} (migration must skip them)"] = sorted(no_go)
    return bad


def main(argv):
    if not os.path.isfile(MAP):
        print(f"no key map at {MAP}")
        return 1
    keymap = json.load(open(MAP, encoding="utf-8"))
    inv_path = os.environ.get("KEYMAP_INVENTORY", "")
    inventory = []
    if inv_path and os.path.isfile(inv_path):
        inventory = [r["ключ"] for r in json.load(open(inv_path, encoding="utf-8"))]
    bad = check(keymap, inventory)
    quiet = "--quiet" in argv
    for what, items in bad.items():
        print(f"\n{what}: {len(items)}")
        if not quiet:
            for it in items[:40]:
                print(f"    {it}")
            if len(items) > 40:
                print(f"    ... and {len(items) - 40} more")
    fatal = sum(len(v) for k, v in bad.items()
                if "SAME OBJECT" in k or "already an ASCII key" in k
                or "not ascii" in k or "not in the map" in k)
    print(f"\nnames in map: {len(keymap)}; inventory: {len(inventory)}; "
          f"fatal problems: {fatal}")
    return 1 if fatal else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
