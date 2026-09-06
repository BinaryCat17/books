"""The on-disk format, declared in one place, with a floor under every key.

WHY THIS FILE EXISTS AT ALL. Of the 243 checks in `tests/`, exactly one opens a
file under `bench/`, and it reads two ASCII fields out of it. Everything else
runs on fixtures built by the same code it is checking. So the suite is blind,
by construction, to the code and the data on disk drifting apart -- and that
drift is the failure mode of every rename in this project.

FOUR TIMES IT WOULD HAVE BEEN SILENT, each measured by experiment:

  `порядок чтения`  renamed in code only: runner 243/242/0 and the mutation
      battery 218/218, both byte-identical to the baseline, while the report
      line flipped from "наш порядок построен так: ранг модели" to "не
      объявлено" on every page of every book.
  `текст размечен`  renamed in code only: on `bench/hard` the line "блоков 49,
      найдено 45 (92%) — считано по 6 страницам из 130" lost its second half.
      The percentage did not move; the knowledge of what it was computed over
      disappeared.
  `ручки`           renamed in code only: `books replay --check` went from "38
      величин в слепке из 55" to 16, and returned 1 both before and after --
      the return code carries no signal here, only the quantity does.
  `вне замера`      renamed in data only: "на объекте вне замера: 350"
      vanished from the report and "лишняя рамка" went 110 -> 460. Three
      hundred and fifty boxes the bench had excluded from scoring were charged
      to the model instead. All five headline numbers stayed put.

HOW THE GUARD WORKS, AND WHY IT IS THE ONLY SHAPE THAT DOES. The key NAME comes
from here -- that is, from the code. The COUNT comes off the disk. A guard that
takes both from the code travels with the code and stays green through any
rename; that was tried, and it stayed green through both directions of a
1228-key experiment. Taking the name from one side and the number from the
other is what makes it fail loudly in both directions:

  code renamed, data not  -> the declared name is not on disk    -> red
  data renamed, code not  -> the declared name fell below floor  -> red

FLOORS ARE MEASURED, NOT GUESSED, and they are floors rather than exact counts
so that adding a bench does not turn the guard red for no reason. They were
counted on tracked files only: `processed/` and the synthetic benches are
absent from git, and a guard that needs them cannot run on a fresh clone.
"""
import collections
import glob as _glob
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class Format:
    """One on-disk format: where its files are, and what must be inside them.

    `floors` is `key -> smallest number of occurrences seen across every
    tracked file of this format`. A key present in the declaration but absent
    from the data is the loudest thing this module can say.
    """

    def __init__(self, name, pattern, floors, note=""):
        self.name = name
        self.pattern = pattern
        self.floors = floors
        self.note = note

    def files(self, root=ROOT):
        return sorted(_glob.glob(os.path.join(root, self.pattern),
                                 recursive=True))


# Counted on 2026-09-06 at commit 4eadd5b over tracked files only.
# Reproduce with:  python3 -m booksmith.schema
FORMATS = (
    Format(
        "truth", "bench/*/truth/*.json",
        {"case": 1366, "book": 1366, "bucket": 2002, "category": 2002,
         "source_category": 3587, "out_of_scope": 1360,
         "objects_out_of_scope": 1359, "text_marked": 1359,
         "order_marked": 1324, "doubtful": 1359, "inexpressible": 1359,
         "file": 1359},
        "1366 tracked pages: 600 annopage, 600 annopage-lite, 130 hard, 36 hard36. "
        "The six synthetic benches are NOT here -- .gitignore closes them "
        "entirely and only their manifest is tracked."),
    Format(
        "dots_pages", "bench/*/dots*/**/*.json",
        {"detector": 1272, "reading_order": 1272, "downscale": 1272,
         "pass_no": 1236, "prompt": 1236, "input_pixel_ceiling": 1236,
         "out_of_vram": 1236, "parse_error": 1236, "answer": 636},
        "Paid output: $0.89 for 600 pages on an RTX 4090, and there is no home "
        "re-parser, so these cannot be regenerated. `порядок чтения` lives here "
        "1272 times and nowhere else in tracked data -- it is the whole floor "
        "under danger O1."),
    Format(
        "detect_run", "bench/*/detect/run.json",
        {"knobs": 3, "value": 72, "default": 72, "what": 72,
         "set_externally": 72, "name": 6, "prompts": 6, "by_label": 6,
         "when": 3, "raster": 3, "commit": 3, "source": 3, "args": 3},
        "Only three detect snapshots are tracked (annopage, hard, hard36); the "
        "other six live behind .gitignore. `books replay --check` walks the "
        "path ('ручки', <knob>, 'значение') -- danger O3."),
    Format(
        "manifest", "bench/*/manifest.json",
        {"book": 146, "value": 210, "default": 210, "what": 210,
         "debt": 210, "set_externally": 210, "page_no": 130, "chars": 99,
         "char_truth": 99, "blocks_with_text": 99, "cell_count": 99},
        "All ten bench manifests are tracked. Note the pair `страниц` (a "
        "number) and `страницы` (a list) living in the SAME object in seven of "
        "them: any rename that maps both onto `pages` drops the list silently "
        "and leaves valid JSON behind."),
)


# THE BOOK IS A FORMAT TOO, and it was the last one nobody declared. `books
# html` writes these names into `book.html` and `books apply` parses the book
# back out with selectors over them (`div[data-уровень="2"]`,
# `[data-оборвано]`). Renaming one in the code left the runner green, the
# battery green, the ratchet green and all five reports identical -- while the
# only real book on disk, 412 swaps and $0.545 of reading, still carried the
# old names and would never be found again.
#
# Declared here so the rename has to be deliberate: the code side is checked
# against this list, and the book on disk is checked against it too.
HTML_ATTRS = (
    "data-без-текста", "data-вид", "data-внутри", "data-доля-в-картинках",
    "data-оборвано", "data-повтор", "data-повтор-текст", "data-пусто",
    "data-роль", "data-скрыто-повторов", "data-стр", "data-текст",
    "data-только-служебное", "data-уровень", "data-форма-таблицы",
    "data-чем", "data-ярлык",
)
HTML_CLASSES = ("лист",)

# The four that EVERY built book must carry, whatever is on its pages. The
# other thirteen are conditional -- `data-без-текста` only appears if some
# sheet has no text on it -- so they cannot be required of a particular book.
# These four are structural: a page marker, a block role, a model label and a
# nesting level are written for every block of every book.
#
# Checked against the book on disk rather than against the code, because that
# is the pairing that drifts: MathJax puts a few dozen data- attributes of its
# own into the same file, so "everything in the book" is not a usable set.
HTML_CORE = ("data-роль", "data-ярлык", "data-стр", "data-уровень")


def measure(root=ROOT):
    """format -> {key: occurrences} over the tracked files, right now."""
    out = {}
    for fmt in FORMATS:
        c = collections.Counter()
        for path in fmt.files(root):
            _walk(json.load(open(path, encoding="utf-8")), c)
        out[fmt.name] = c
    return out


def _walk(obj, counter):
    if isinstance(obj, dict):
        for k, v in obj.items():
            counter[k] += 1
            _walk(v, counter)
    elif isinstance(obj, list):
        for v in obj:
            _walk(v, counter)


def below_floor(root=ROOT):
    """[(format, key, floor, found)] -- empty means code and data agree."""
    bad = []
    seen = measure(root)
    for fmt in FORMATS:
        got = seen[fmt.name]
        for key, floor in sorted(fmt.floors.items()):
            if got.get(key, 0) < floor:
                bad.append((fmt.name, key, floor, got.get(key, 0)))
    return bad


def main():
    for fmt in FORMATS:
        files = fmt.files()
        print(f"\n=== {fmt.name}: {len(files)} files  ({fmt.pattern})")
        c = collections.Counter()
        for path in files:
            _walk(json.load(open(path, encoding="utf-8")), c)
        for key, floor in sorted(fmt.floors.items(), key=lambda kv: -kv[1]):
            got = c.get(key, 0)
            mark = "  " if got >= floor else "LOW"
            print(f"  {mark} {got:>7} / {floor:<7} {key}")
    bad = below_floor()
    print(f"\nkeys below floor: {len(bad)}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
