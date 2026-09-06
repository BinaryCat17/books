"""Second contour detector: docling heron (IBM), RT-DETRv2 on ResNet-50.

WHY A SECOND MODEL WHEN THE FIRST IS NOT BEING REPLACED. The bench measured a
defect in PP-DocLayoutV2: two tables side by side merge into one box -- 0 split
of 3 pages, against 100% on `image`, `chart` and `header`. "A flaw of DETR
one-to-one matching" and "a flaw of a training set where tables are 1.18% and
nearly all single" cannot be told apart from one model, so the second has to be
independent: another architecture (RT-DETRv2 against RT-DETR-L), other data
(150k IBM documents against 30k Baidu), another input (640/800).

WHAT IT CANNOT DO, TO BE KNOWN BEFORE MEASURING:

* **No reading order.** docling computes it by rules, apart from the model.
  `Block.order` here is the position in our list -- a VALUE declared as such in
  the fingerprint, not a model rank. The order metric may not be run on it.
* **No `chart` class at all** -- charts leave as `picture`. A difference of
  vocabularies, not an error of the model.
* **No page number of its own** -- it lives inside `page_footer`.

At `DOCLING_PIPELINE=off`, the default, NOT ONE LINE of docling postprocessing
runs here (`LayoutPostprocessor`: per-class thresholds, three box-refinement
passes, merging of nested boxes). We call the graph directly: project rule,
what the model gave is what gets measured.

THE DOCLING PIPELINE IS A KNOB, NOT A DEFAULT. `post|full` turns on two VENDOR
classes, called as they are, with no edit of ours inside:

* `docling.utils.layout_postprocessor.LayoutPostprocessor` -- thresholds PER
  CLASS (SEVENTEEN of them: 0.5 for caption, footnote, formula, list_item,
  page_footer, page_header, picture, table, text; 0.45 for section_header,
  title, code, document_index, form, key_value_region, checkbox_selected,
  checkbox_unselected), overlap resolution over three ranks (regular/picture/
  wrapper, each with its own area_threshold and conf_threshold), suppression
  of coincident pairs at IoU > 0.8, `TITLE -> SECTION_HEADER`, and boxes that
  fall inside a wrapper going INTO ITS CHILDREN (734 of 15689 on the golden
  bench). The thresholds are the pipeline's first act and here they remove not
  one box -- that, and what the children cost, is measured at
  `_DoclingPipeline.apply`.
* `docling.models.postprocessing.reading_order_rb.ReadingOrderPredictor` --
  "rb" is RULE-BASED, and that has to be said aloud: 740 lines of RULES over
  boxes, not one weight. heron predicts no reading order with the knob or
  without it; the pipeline swaps OUR sorting rule for THEIRS, which is why our
  answers still begin with "ours" (the contract is at `ORDER_RULE`).

The project rule "nobody fixes the model" is NOT broken, for exactly two
reasons, both required: the vendor code is called unedited (we merge and move
no box ourselves) and it is switched on by a declared knob, not silently. A
patch is when WE fix a box.

What it buys and what it costs, in full: `run/knobs.py`, `DOCLING_PIPELINE`.
Briefly, on 600 golden pages (`off` against `full`): boxes 15689 -> 9867,
duplicate pairs at IoU>=0.9 4435 -> 19, VLM requests 23.0 -> 14.6 per page,
extra column jumps 2718 -> 471 IN COUNT (over all 600 pages that is 4.53 ->
0.79, while today's `metrics.column_jumps` divides by the pages that made the
count and prints 5.24 -> 1.06: the same counts, another denominator -- which
is why counts stand here).

Ink is not the whole price, and that is the point of the paragraph. In ink:
whole objects 1049 -> 1042 of 1230, outside every box 24.6% -> 26.3%, TORN 127
-> 135. By the measure that penalises merging it is three times dearer:
artefacts found 694 -> 562, meaning intact 602 -> 500, MERGES 366 -> 461.
`books fitness` does not penalise merging by construction, so judging the
pipeline by ink alone would name a price of seven objects instead of a hundred
and thirty-two. Exactly why the knob defaults to OFF and the book is based on
PP-DocLayoutV2: its reading rank is its own, and its merges 375 against 461.

`post` CHANGES THE ORDER TOO: its last act is to sort the list itself, by
exact `(top, left)` (the key, and why it degenerates, at `ORDER_RULE`). On 13
pages of `bench/slovar` its output matched a sort by (t, l) on 13 of 13 and
our key `(round(y/20), x)` on 3, with 237 boxes out of place on 10 pages; and
it is not free -- 474 extra column jumps under `post` against 453 for the very
same boxes resorted by our key. So `post` makes the order WORSE; only `full`
repairs it, 0.79 jumps per page. BOTH THOSE NUMBERS WERE TAKEN ON THE KEY
`(round(y/20), x)`, WHICH AT `off` NO LONGER EXISTS: the assembly rule moved
to `booksmith/order.py` (section 20 of `docs/contour-notes.md`), where at `off`
the declared `(y0, x0)` or the docling rules act by `ASSEMBLY_ORDER`; the
bucket key survives for one job only, the numbering before the vendor pipeline
(`_our_order`). The `post` number 474 is not moved by that -- the vendor sorts
there -- and 453 is historical.
"""
import hashlib
import json
import os
import sys

from .base import Block, Page, Recognizer
# The role of a label is OUR policy and lives in one place. Needed here for
# one number: artefact boxes the vendor took into the children of a TEXT
# wrapper, that is, lost for the book. A list of classes of our own here would
# be a second vocabulary of roles, and those have diverged before.
from .. import order
from .. import policy
from ..run import knobs

MODELS = os.path.expanduser("~/.paddlex/official_models")


class WeightsMissing(RuntimeError):
    pass


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# --- docling vendor pipeline: label translation ----------------------------

# The egret and heron vocabularies are ONE set of 17 docling classes written
# differently in the weights: heron in snake_case (`page_header`), egret in
# display names (`Page-header`, `Document Index`, `Key-Value Region`). The
# translation is declared BY NAME, not derived by "lowercase it, hyphen into
# underscore": such a rule would silently accept an eighteenth class of new
# weights and hand it to the vendor under an invented name, and an invented
# label is worse than a refusal. A label missing here fails the run aloud.
EGRET_TO_DOCLING = {
    "Caption": "caption",
    "Checkbox-Selected": "checkbox_selected",
    "Checkbox-Unselected": "checkbox_unselected",
    "Code": "code",
    "Document Index": "document_index",
    "Footnote": "footnote",
    "Form": "form",
    "Formula": "formula",
    "Key-Value Region": "key_value_region",
    "List-item": "list_item",
    "Page-footer": "page_footer",
    "Page-header": "page_header",
    "Picture": "picture",
    "Section-header": "section_header",
    "Table": "table",
    "Text": "text",
    "Title": "title",
}

# What the knob can do. `off` -- the model boxes as they are; `post` -- the
# postprocessor alone (it changes the boxes and resorts them itself); `full`
# -- that plus the reading-order rules. TWO enabling values and not one "on",
# because the effects differ and have to be separable: `post` moves and
# collapses boxes (15643 -> 9817), `full` on top of that permutes them without
# touching geometry. Merged, they would say "better" without saying from what.
PIPELINE_MODES = ("off", "post", "full")

_PIP_INSTALL = ('pip install -e ".[docling]"  (docling-slim==2.123.1 and '
                'rtree; no torch, +54 MB)')


class _DoclingPipeline:
    """Two vendor docling classes over the boxes of our adapter.

    NOT ONE EDIT OF OURS INSIDE THE FOREIGN CODE. Ours here is exactly three
    things, each of them silently dangerous, so each is named apart.

    1. THE ORIGIN. Our boxes count from the TOP LEFT corner (`base.py`), while
       the order rules compare elements through `self.b > other.b`, that is,
       expect a BOTTOM origin. Feed ours as they are and the book is read
       bottom up, and NO box metric notices: the boxes are the same. docling
       converts it itself
       (`models/stages/reading_order/readingorder_model.py:69`), so do we --
       `bbox.to_bottom_left_origin(page height)`.
    2. THE LABEL TRANSLATION (`EGRET_TO_DOCLING`), by name, checked whole at
       construction rather than page by page (why, at the check itself).
    3. WE HAVE NO TEXT CELLS. We count on the raster, not on the PDF text
       layer, hence `skip_cell_assignment=True`: otherwise the postprocessor
       would fit boxes to cells that do not exist -- no longer its work but
       our invention by its hands.

    OUTWARD THE LABEL COMES BACK IN THE ADAPTER'S SPELLING: `policy.py` knows
    the `Docling` and `Docling-egret` vocabularies apart and `detect.py` calls
    `policy.check` by the model's, so substituting the spelling would kill the
    egret run on its own bench. Translation goes to the vendor and back only.
    """

    def __init__(self, mode: str, labels, adapter: str):
        if mode not in PIPELINE_MODES:
            raise SystemExit(f"DOCLING_PIPELINE={mode!r}: I know only "
                             f"{PIPELINE_MODES}")
        self.mode = mode
        self.adapter = adapter
        # Lazy import and a clear refusal: without the knob the adapter must
        # count with no package at all, with the knob and no package it must
        # fail aloud and name what to install.
        try:
            import docling
            from docling.datamodel.base_models import Cluster, Page as DlPage
            from docling.datamodel.pipeline_options import (
                BaseLayoutPostprocessorOptions)
            from docling.utils.layout_postprocessor import LayoutPostprocessor
            from docling.models.postprocessing.reading_order_rb import (
                PageElement as RoElement, ReadingOrderPredictor)
            from docling_core.types.doc import BoundingBox, DocItemLabel, Size
        except ImportError as e:
            raise SystemExit(
                f"DOCLING_PIPELINE={mode}, and there is no docling "
                f"package: {e}. Install: {_PIP_INSTALL}. Or "
                f"DOCLING_PIPELINE=off -- then the adapter counts the model "
                f"boxes as they are and the package is not needed at all."
                ) from None
        self._Cluster, self._DlPage = Cluster, DlPage
        self._BoundingBox, self._DocItemLabel, self._Size = (
            BoundingBox, DocItemLabel, Size)
        self._LayoutPostprocessor = LayoutPostprocessor
        self._RoElement = RoElement
        # The order predictor is held ONE per run: its constructor sets two
        # numbers of its own (`dilated_page_element`, horizontal expansion
        # threshold 0.15), and rebuilding it per page would promise they drift.
        self._ro = ReadingOrderPredictor() if mode == "full" else None
        self.options = BaseLayoutPostprocessorOptions(skip_cell_assignment=True)

        # THE LABEL TRANSLATION IS CHECKED WHOLE, AT ONCE, AND AGAINST THE
        # VOCABULARY THAT WILL ACTUALLY BE ASKED -- an untranslatable class
        # then kills the run on page zero, not on page four hundred after
        # twenty minutes. `DocItemLabel` is not that vocabulary: it holds 30
        # names against the seventeen the postprocessor knows
        # (`LayoutPostprocessor.CONFIDENCE_THRESHOLDS`), and the threshold is
        # taken from that dict WITH NO DEFAULT. Thirteen names passed silently
        # -- chart, paragraph, reference, handwritten_text, marker,
        # grading_scale, empty_value and six field_* -- and the first page died
        # with a bare `KeyError <DocItemLabel.CHART>` after the graph was up.
        # Reproduced: `_DoclingPipeline("post", DEFAULT_LABELS+["chart"],
        # "docling-heron")` built SILENTLY (18 labels) and died on page zero.
        # `chart` is exactly the class the header calls the main difference.
        known = {lab.value for lab in
                 LayoutPostprocessor.CONFIDENCE_THRESHOLDS}
        self.to_docling = {lab: EGRET_TO_DOCLING.get(lab, lab) for lab in labels}
        bad = []
        for lab, name in self.to_docling.items():
            try:
                DocItemLabel(name)
            except ValueError:
                bad.append(f"{lab!r} (-> {name!r}: no such name in the "
                           f"docling vocabulary at all)")
                continue
            if name not in known:
                bad.append(f"{lab!r} (-> {name!r}: the name is in the "
                           f"docling vocabulary, but the postprocessor has "
                           f"no threshold for it)")
        if bad:
            raise SystemExit(
                f"adapter {adapter}: labels {', '.join(bad)} are "
                f"indigestible to the docling postprocessor. It knows "
                f"{len(known)} classes -- those listed in "
                f"LayoutPostprocessor.CONFIDENCE_THRESHOLDS -- and takes the "
                f"threshold by label with NO default, so on any other it "
                f"dies with KeyError on the very first page. The translation "
                f"is declared BY NAME in EGRET_TO_DOCLING "
                f"(models/docling_heron.py): a rule 'lower-case it' would "
                f"silently accept a new class of new weights and slip it to "
                f"the vendor under an invented name.")
        self.back = {v: k for k, v in self.to_docling.items() if v != k}

        # sha256 of BOTH files: they are the rules. A vendor edit changes our
        # boxes and our order silently, while the package version need not move
        # at all (an edit in a branch, a local patch, `pip install -e`).
        self.files = {}
        for cls in (LayoutPostprocessor, ReadingOrderPredictor):
            path = sys.modules[cls.__module__].__file__
            self.files[os.path.basename(path)] = _sha256(path)
        self.version = getattr(docling, "__version__", None)

        # Run counters. Numbers, not "done": without them "the pipeline is on"
        # is indistinguishable from "the pipeline is on and did nothing".
        # "REORDERED" IS COUNTED TWICE, because TWO things reorder. One
        # counter, and it counted only inside the `full` branch, sent a zero
        # from no-check into the meta of every page, into the log and into
        # `run.json`, printed as a zero from measurement -- while the
        # postprocessor does resort: on `bench/slovar` 237 boxes of 531.
        self.pages = self.before = self.after = self.kids = 0
        self.displaced = 0           # total: out of place against ours
        self.resorted = 0            # postprocessor sort: both modes
        self.reordered = 0           # reading-order rules: `full` only
        self.arte_in_text = 0        # artefact into a TEXT wrapper's children
        self.arte_lost = 0           # ...and not left on the top level

    # The order line MUST begin with the word "ours": by it
    # `metrics._model_has_rank` learns there is no model rank here and prints
    # no percentage out of nothing. The rule is named by name as well, so that
    # "ours" is not read as "top down" when it is no longer top down.
    ORDER_RULE = {
        # `post` CHANGES THE ORDER.
        # `LayoutPostprocessor._sort_clusters(mode="id")` takes a key of three
        # members: `min(cell.index) if cluster.cells else sys.maxsize`, then
        # `bbox.t`, then `bbox.l`. Our `cluster.cells` are ALWAYS empty --
        # `skip_cell_assignment=True` is set by us -- so the first member
        # degenerates into a constant and exact `(top, left)` remain, NOT our
        # `round(y/20)` bands. The price of calling a foreign order ours was
        # paid on hard36, where seven benches printed "pairs 211, agreed 73%"
        # over a truth that marks no reading order on any page at all.
        "post": "ours_only_in_the_sense_that_the_model_gave_no_rank: the rule "
                "is FOREIGN -- the docling postprocessor resorted the boxes "
                "by (top, left), exact coordinates, not by our round(y/20) "
                "bands",
        "full": "ours_by_choice_rules_are_doclings_reading_order_rb: RULE-BASED, "
                "740 lines of rules without a single weight, not a model",
    }

    def _label(self, raw):
        """Adapter label -> docling label. An unknown one aloud, not KeyError.

        Reaching here with a foreign label is only possible past `read()`, but
        "KeyError: 'Chart'" would not say WHAT to fix, and the fix is one line
        in `EGRET_TO_DOCLING`.
        """
        try:
            return self._DocItemLabel(self.to_docling[raw])
        except KeyError:
            raise RuntimeError(
                f"label {raw!r} is not from the {self.adapter} weights "
                f"vocabulary: it has no translation into docling's. Declare "
                f"it in EGRET_TO_DOCLING by name.") from None

    def apply(self, blocks, width, height, index):
        """Adapter boxes -> boxes after the vendor. Returns (blocks, meta)."""
        clusters = [
            self._Cluster(
                id=b.block_id, label=self._label(b.label),
                bbox=self._BoundingBox(l=b.box[0], t=b.box[1],
                                       r=b.box[2], b=b.box[3]),
                confidence=b.score, cells=[], children=[])
            for b in blocks]

        resorted = None
        if self.mode in ("post", "full"):
            page = self._DlPage(page_no=index)
            page.size = self._Size(width=float(width), height=float(height))
            # THE POSTPROCESSOR'S FIRST ACT -- THE PER-CLASS THRESHOLDS -- IS
            # DEAD HERE, so that its work is not credited with someone else's.
            # All seventeen vendor thresholds are at most 0.5, while our
            # selection in `read()` has already cut by
            # `LAYOUT_SCORE_THRESHOLD`, whose default is the same 0.5. Measured
            # (matematika + slovar, heron and egret, four `off` runs): 1948
            # boxes, ZERO below their own vendor threshold, minimum confidence
            # 0.50033 against the highest vendor threshold of exactly 0.5. The
            # step comes alive only below 0.45, where the eight 0.45 classes
            # lose boxes first.
            clusters = self._LayoutPostprocessor(
                page, clusters, self.options).postprocess()
            # HOW MANY BOXES THE POSTPROCESSOR ITSELF RESORTED, counted in
            # BOTH modes because it sorts in both. The comparison is against
            # our numbers (`Cluster.id`), not against the length of the list:
            # thinning shifts everyone, and what must be measured is the
            # permutation of the survivors, not their loss.
            ids = [c.id for c in clusters]
            resorted = sum(1 for a, b in zip(ids, sorted(ids)) if a != b)

        # At `post` the reading-order rules are NOT CALLED AT ALL, so their
        # number here is a dash: a zero from no-check and a zero from
        # measurement are different zeros, and the first stood here as second.
        moved = 0 if self.mode == "full" else None
        if self.mode == "full" and clusters:
            size = self._Size(width=float(width), height=float(height))
            els = []
            for i, c in enumerate(clusters):
                bb = c.bbox.to_bottom_left_origin(float(height))
                els.append(self._RoElement(
                    cid=i, text="", page_no=index, page_size=size,
                    label=c.label, l=bb.l, r=bb.r, b=bb.b, t=bb.t,
                    coord_origin=bb.coord_origin))
            # THE ORDER DEPENDS ON THE PYTHON VERSION -- not our trouble, but
            # our care. `reading_order_rb.py` holds TWO non-transitive
            # `sorted()` calls, both sorting `PageElement` by the same
            # `__lt__` ("overlapping horizontally -- compare by the bottom,
            # else by the left edge"): line 535 `_find_heads`, line 556
            # `_sort_ud_maps`, and 556 is the one that diverged in the
            # measurement. For an inconsistent comparison the answer of
            # `sorted` depends on the order in which pairs get compared.
            # Measured: the same 600 pages, docling 2.123.1, pydantic 2.13.5,
            # numpy 2.5.2 -- on python 3.12.3 and 3.13.13 the order diverged on
            # THREE pages of 600 (0001, 0129, 0482), the boxes the same to the
            # last digit and the set the same, only the places permuted, which
            # no box metric sees. ON OUR TWO BOOKS IT IS INVISIBLE, and that is
            # a measured zero, not a skipped check: substituting the name
            # `sorted` in the vendor module's namespace (its code untouched)
            # over 25 pages of slovar+matematika gave 75 calls of `_find_heads`
            # (7 lists of three elements or more) against 684 of
            # `_sort_ud_maps` (13 lists) -- 0 non-transitive triples in either,
            # so hunt it on a bigger bench. Within one python it repeats byte
            # for byte (three runs); the version goes into the fingerprint
            # (`detect.py:_packages`), so a divergence is at least visible.
            order = [e.cid for e in self._ro.predict_reading_order(els)]
            # A permutation must be a permutation. The rules split running
            # heads and body into three lists and sew them back; lose an
            # element there and a box would vanish from the book silently,
            # while the count "after" would merely look a little smaller.
            if sorted(order) != list(range(len(clusters))):
                raise RuntimeError(
                    f"the docling order rules returned no permutation on "
                    f"page {index}: there were {len(clusters)} boxes, "
                    f"{len(order)} numbers came back")
            moved = sum(1 for i, j in enumerate(order) if i != j)
            clusters = [clusters[i] for i in order]

        # TOTAL DISPLACEMENT AGAINST OUR ORDER -- one number, over the final
        # list: how many surviving boxes stand elsewhere than our numbering
        # (`Cluster.id`, our `(round(y/20), x)` key) would put them. This goes
        # to `detect.py` as "boxes reordered", which sums it over pages and
        # prints the total; the two fields below split it into causes.
        final_ids = [c.id for c in clusters]
        displaced = sum(1 for a, b in zip(final_ids, sorted(final_ids))
                        if a != b)
        # WHO STAYED ON TOP. Going into children and vanishing from the book
        # are not the same thing, and only this set tells them apart: the
        # vendor takes children off the top list for table and picture
        # wrappers only (`TABLE_TYPES`, `PICTURE`). Checked by substitution:
        # `document_index <- formula` leaves one `document_index` box on top
        # and no formula at all; `key_value_region <- formula` leaves both.
        top = set(final_ids)

        out, kids, arte_in_text, arte_lost = [], {}, 0, 0
        for i, c in enumerate(clusters):
            lab = self.back.get(c.label.value, c.label.value)
            # CHILDREN DESCRIBE THEMSELVES, NOT BY A NUMBER IN A FOREIGN
            # NUMBERING. Here lay `{i: [k.id, ...]}`: the key from after the
            # pipeline, the values from before it, and nothing tying one to
            # the other -- the boxes are renumbered from zero and keep no
            # pre-pipeline number, so it could be recovered only by a second
            # run with `DOCLING_PIPELINE=off`. Now the key is the wrapper's
            # position in this same list, and the child carries its own label,
            # box and number, each named by a field.
            ch = [{"id_before_pipeline": int(k.id),
                   "label": self.back.get(k.label.value, k.label.value),
                   "box": [k.bbox.l, k.bbox.t, k.bbox.r, k.bbox.b]}
                  for k in c.children]
            if ch:
                kids[i] = ch
                # LOSS OF STRUCTURE IS A NUMBER OF ITS OWN, AND THERE ARE TWO
                # OF THEM. First: an artefact (table, picture, formula, code)
                # went into the children of a TEXT wrapper -- `document_index`,
                # `form`, `key_value_region`. Second, stricter: it is gone from
                # the top list as well, so the wrapper leaves as text and
                # no one is left to cut the artefact out of it (which wrappers
                # lose their children is measured just above). The 734
                # children of the golden bench BY WRAPPER: picture 526,
                # key_value_region 161, document_index 26, table 21;
                # artefact boxes in text wrappers among them 6. On
                # `bench/hard36` (36 pages, heron, post) that number is
                # ZERO, and a counted zero: 60 children, 49 in `picture`
                # wrappers and 11 in `key_value_region`; by label text 40,
                # caption 10, section_header 9, formula 1, and the one
                # artefact (formula) went into a PICTURE wrapper, which level
                # two cuts whole.
                if policy.role(lab) == "text":
                    art = [k for k in ch
                           if policy.role(k["label"]) == "artifact"]
                    arte_in_text += len(art)
                    arte_lost += sum(1 for k in art
                                     if k["id_before_pipeline"] not in top)
            out.append(Block(
                block_id=i,
                box=(c.bbox.l, c.bbox.t, c.bbox.r, c.bbox.b),
                label=lab, score=c.confidence, order=i))

        self.pages += 1
        self.before += len(blocks)
        self.after += len(out)
        self.kids += sum(len(v) for v in kids.values())
        self.displaced += displaced
        self.resorted += resorted or 0
        self.reordered += moved or 0
        self.arte_in_text += arte_in_text
        self.arte_lost += arte_lost
        meta = {
            "mode": self.mode,
            "boxes_before": len(blocks),
            "boxes_after": len(out),
            "moved_to_children": sum(len(v) for v in kids.values()),
            # THREE NUMBERS INSTEAD OF ONE, EACH ANSWERING ITS OWN QUESTION.
            # The first is the total: how many boxes stand elsewhere than our
            # order would put them; `detect.py` reads it and sums it over the
            # book, so the field keeps its name. The second and the third name
            # the CAUSES, and they DO NOT ADD UP to the first, nor should
            # they: they are measured at different steps -- the postprocessor
            # sort (both modes) on its own output, the order rules (`full`
            # only) on theirs. On slovar: total 354, sort 237, rules 372.
            "boxes_reordered": displaced,
            "reordered_by_postprocessor_sort": resorted,
            "reordered_by_order_rules": moved,
            # The key is the wrapper's position IN THIS list; every child
            # carries its own pre-pipeline number in a field. Both are named.
            "children_by_box_index": kids,
            # Not "how much collapsed" but how much was LOST by it: artefacts
            # taken into the children of a TEXT wrapper, and those of them no
            # longer on the top list at all -- a direct loss of structure.
            "artifact_boxes_in_text_wrappers": arte_in_text,
            "of_those_lost_from_top_level": arte_lost,
        }
        return out, meta

    def fingerprint(self):
        return {
            "mode": self.mode,
            "what_is_it": ("VENDOR code, called as it is, without one edit "
                        "of ours inside; reading_order_rb is rule-based, 740 "
                        "lines of rules over boxes, not a single weight"),
            "classes": ["docling.utils.layout_postprocessor.LayoutPostprocessor"]
                      + (["docling.models.postprocessing.reading_order_rb."
                          "ReadingOrderPredictor"] if self.mode == "full"
                         else []),
            "docling_version": self.version,
            "sha256_vendor_files": self.files,
            "postprocess_options": self.options.model_dump(mode="json"),
            "label_map_to_docling": self.to_docling,
            "label_outward": "in the adapter's spelling",
            "summary": {"page_count": self.pages, "boxes_before": self.before,
                     "boxes_after": self.after, "moved_to_children": self.kids,
                     "boxes_reordered": self.displaced,
                     "reordered_by_postprocessor_sort": self.resorted,
                     # A dash, not a zero: at `post` the order rules
                     # were never called.
                     "reordered_by_order_rules":
                         self.reordered if self.mode == "full" else None,
                     "artifact_boxes_in_text_wrappers":
                         self.arte_in_text,
                     "of_those_lost_from_top_level": self.arte_lost},
        }


class DoclingHeron(Recognizer):
    name = "docling-heron"
    policy_name = "Docling"

    def __init__(self, model_dir: str | None = None):
        import onnxruntime as ort

        self.dir = model_dir or os.path.join(MODELS, "docling-heron_onnx")
        self.onnx = os.path.join(self.dir, "model.onnx")
        cfg_path = os.path.join(self.dir, "config.json")
        pre_path = os.path.join(self.dir, "preprocessor_config.json")
        missing = [p for p in (self.onnx, cfg_path, pre_path)
                   if not os.path.exists(p)]
        if missing:
            raise WeightsMissing(
                f"no docling heron weights: {missing}. Download three "
                f"files from "
                f"huggingface.co/docling-project/docling-layout-heron-onnx "
                f"into {self.dir}")
        with open(cfg_path, encoding="utf-8") as f:
            cfg = json.load(f)
        i2l = cfg.get("id2label") or {}
        # The label vocabulary MUST come from the weights. The ONNX build of
        # heron has none in `config.json` -- then the list declared here, and
        # an index beyond it fails: an invented label is worse than a refusal.
        self.labels = ([i2l[str(i)] for i in range(len(i2l))] if i2l
                       else list(DEFAULT_LABELS))
        # The knob is read HERE AND ONCE per run, not on every page:
        # `os.environ` is alive, and a run with half its pages counted by one
        # rule and half by another would be irreproducible while `run.json`
        # named a single value. The pipeline is built BEFORE the ONNX session:
        # refusing with "no docling package" costs milliseconds and raising
        # the graph costs seconds, so failing must happen on the cheap one.
        self.pipeline = knobs.knob("DOCLING_PIPELINE")
        self._pipe = (None if self.pipeline == "off"
                      else _DoclingPipeline(self.pipeline, self.labels,
                                            self.name))
        with open(pre_path, encoding="utf-8") as f:
            pre = json.load(f)
        size = pre.get("size") or {}
        self.target_h = int(size.get("height", 640))
        self.target_w = int(size.get("width", 640))
        # THE FILTER IS TRANSLATED, NOT PASSED ON AS A NUMBER. The weights
        # record `resample` as a PIL code, we resize through cv2, and their
        # numbers DIFFER: PIL 2 is BILINEAR, cv2 2 is INTER_CUBIC. Passing the
        # number silently, we shrank the page with a filter other than the one
        # used in training, and nothing could catch it: boxes stay plausible.
        pil = int(pre.get("resample", 2))
        # PIL: 0 NEAREST, 1 LANCZOS, 2 BILINEAR, 3 BICUBIC, 4 BOX, 5 HAMMING
        # cv2: 0 NEAREST, 1 LINEAR, 2 CUBIC, 3 AREA, 4 LANCZOS4
        PIL_TO_CV2 = {0: 0, 1: 4, 2: 1, 3: 2, 4: 3, 5: 3}
        if pil not in PIL_TO_CV2:
            raise WeightsMissing(
                f"unknown filter code resample={pil} in the preprocessor: "
                f"substituting our own would shrink the page with the wrong "
                f"filter.")
        self.interp_pil = pil
        self.interp = PIL_TO_CV2[pil]
        self.do_pad = bool(pre.get("do_pad", False))
        if self.do_pad:
            raise WeightsMissing(
                "the preprocessor says do_pad: true, and we shrink the "
                "raster with no padding -- the boxes would come out shifted "
                "and plausible at once.")
        self.do_rescale = bool(pre.get("do_rescale", False))
        self.do_normalize = bool(pre.get("do_normalize", False))
        self.sess = ort.InferenceSession(
            self.onnx, providers=["CPUExecutionProvider"])
        self.ort_version = ort.__version__
        self.providers = list(self.sess.get_providers())
        kinds = {i.name: i.type for i in self.sess.get_inputs()}
        self.uint8_input = "uint8" in kinds.get("images", "")

    def _our_order(self, kept, w, h, index):
        """Our assembly order -- and ONLY where it is truly ours.

        TWO DIFFERENT CASES, AND THEY USED TO BE ONE. At
        `DOCLING_PIPELINE=off` this list IS the book, so the order comes from
        `order.py` -- one rule for the project, declared by `ASSEMBLY_ORDER`.
        At `post` and `full` the order is set by the VENDOR: the postprocessor
        sorts the list itself, and `full` calls the reading rules on top. Our
        sort there is not a reading order but a NUMBERING: the box number is
        `Cluster.id`, by which the vendor stitches children to their wrapper,
        and were we to permute afterwards the "children" would point nowhere.

        So with the pipeline on the key stays byte for byte as it was:
        `(round(y/20), x)`. A bucket key, no good as a reading order, but only
        a stable numbering is wanted from it here, and changing it would shift
        every number of sections 18 and 19, which were taken on it -- and
        changing what has been measured along with a fix leaves it unknown
        which of the changes belongs to whom.
        """
        if self._pipe is not None:
            kept.sort(key=lambda t: (round(t[2][1] / 20), t[2][0]))
            return kept
        # The rule is asked ONCE and passed on: two separate `rule()` calls
        # would read the environment twice per page, and an edit of the knob
        # mid-run would part the guard from the sort.
        which = order.rule()
        order.cover(self.labels, which)
        perm = order.permutation([t[0] for t in kept], [t[2] for t in kept],
                                 w, h, index, self.labels, which)
        return [kept[i] for i in perm]

    def _run_pipeline(self, blocks, w, h, index):
        """Model boxes -> boxes after the vendor. Returns (blocks, meta).

        At `off` it does nothing and returns our previous order. The order
        line is handed out FROM HERE always, not written in `read()` as a
        constant: a constant would survive the pipeline being switched on and
        would lie to the metric that the order is still ours.

        Numbers into the log every ten pages, at the rate of `books detect`
        itself, by `print` and not by its `log`: the adapter has no access to
        the command's log, and "the pipeline is on" without numbers is
        indistinguishable from "on and did nothing".
        """
        if self._pipe is None:
            # The words come from `order.py`, not from a constant here: a
            # constant once said "ours, top down and left to right" while the
            # sort was `(round(y/20), x)`, buckets of twenty raster pixels --
            # two rules under one name, catchable only by reading both places.
            return blocks, {"reading_order": order.WORDS[order.rule()]}
        blocks, m = self._pipe.apply(blocks, w, h, index)
        pp = self._pipe
        if pp.pages == 1 or pp.pages % 10 == 0:
            print(f"  [docling pipeline {pp.mode}] {pp.pages} pp.: boxes "
                  f"{pp.before} -> {pp.after}, into children {pp.kids} (of "
                  f"those, artefacts in text wrappers {pp.arte_in_text}, "
                  f"lost {pp.arte_lost}), "
                  f"out of place {pp.displaced} (the sort moved "
                  f"{pp.resorted}, the rules permuted "
                  + (str(pp.reordered) if pp.mode == "full"
                     else "-- (never called)") + ")")
        return blocks, {"reading_order": _DoclingPipeline.ORDER_RULE[pp.mode],
                        "docling_pipeline": m}

    def thresholds(self) -> dict[str, float]:
        """The threshold per class. This build has no native `draw_threshold`,
        so the common knob is taken -- and said outright, so that the number
        does not look like a foreign default."""
        common = float(knobs.knob("LAYOUT_SCORE_THRESHOLD"))
        return {lab: common for lab in self.labels}

    def threshold_drift(self) -> list[str]:
        """How the acting threshold differs from the native one of the weights.

        This build HAS no native threshold: `config.json` holds no
        `draw_threshold`, and docling keeps its seventeen thresholds in the
        pipeline code, not in the weights. So the guard says honestly that
        there is nothing to compare with -- which is not the same as "no
        drift".
        """
        return [f"the weights have no native threshold; acting is "
                f"LAYOUT_SCORE_THRESHOLD="
                f"{knobs.knob('LAYOUT_SCORE_THRESHOLD')} "
                f"on all {len(self.labels)} classes"]

    def knobs_read(self) -> tuple[str, ...]:
        """Exactly the two below, and that is checked by grep over the file.

        `knobs.knob()` is called three times here: twice with
        LAYOUT_SCORE_THRESHOLD (`thresholds`, `threshold_drift`) and once with
        DOCLING_PIPELINE (`__init__`, once per run). What is NOT here and why:
        the weights directory is hardwired in `__init__`, so LAYOUT_MODEL_DIR
        and LAYOUT_MODEL_NAME never reach this file; LAYOUT_TABLE_THRESHOLD is
        read by nothing -- `table` takes the same common threshold as the other
        sixteen. Before this declaration the fingerprint of a heron run named
        all three, LAYOUT_MODEL_NAME reading `PP-DocLayoutV2`, a foreign model.

        `DoclingEgret` inherits the list not out of laziness: it has no
        `knob()` of its own, takes the threshold through the same
        `self.thresholds()` and the pipeline through the same `__init__`.

        Leaving DOCLING_PIPELINE undeclared would give the fingerprint back the
        disease this field exists against: the `run.json` of two runs differing
        in EVERYTHING -- 15643 boxes against 9817, a foreign order rule instead
        of ours -- would become indistinguishable, because the value that
        decided the difference is marked in it "not relevant to this run".
        """
        return ("LAYOUT_SCORE_THRESHOLD", "DOCLING_PIPELINE")

    def label_map(self) -> dict[str, str]:
        """Labels are NOT translated into the PP-DocLayoutV2 vocabulary.

        Reducing `picture` to `image` and `formula` to `display_formula` would
        erase the difference of vocabularies: docling has no `chart` at all,
        and after such a reduction "a chart called a picture" would be
        indistinguishable from "a chart found". Matching is blind to the
        label, and the labels themselves are stored as they are.
        """
        return {}

    def fingerprint(self) -> dict:
        # THE PIPELINE TOTAL -- AS A NUMBER AND INTO THE LOG, exactly once per
        # run. The adapter has no "run finished" hook, and `detect.py` calls
        # `fingerprint()` four times: three BEFORE the page loop (the counter
        # is empty, nothing to print) and once AFTER, before writing
        # `run.json`; the condition "pages > 0" puts this line in the only
        # right place. A value invisible in the log is not checked against the
        # expected one, on which this project has already lost evenings.
        if self._pipe is not None and self._pipe.pages:
            it = self._pipe.fingerprint()["summary"]
            share = (100.0 * it["boxes_after"] / it["boxes_before"]
                    if it["boxes_before"] else 0.0)
            rules = (str(it["reordered_by_order_rules"])
                       if self._pipe.mode == "full" else "-- (never called)")
            # `post` DOES change the order: the postprocessor sorts by exact
            # (top, left), not by our round(y/20) key.
            order = ("VENDOR RULES (reading_order_rb, not a model)"
                       if self._pipe.mode == "full" else
                       "resorted by the docling postprocessor by "
                       "(top, left), there is no model rank")
            print(f"docling pipeline {self._pipe.mode}: pages "
                  f"{it['page_count']}, boxes {it['boxes_before']} -> "
                  f"{it['boxes_after']} ({share:.1f}%), into children "
                  f"{it['moved_to_children']}, of those artefacts in text "
                  f"wrappers {it['artifact_boxes_in_text_wrappers']} "
                  f"(lost from the top list "
                  f"{it['of_those_lost_from_top_level']}); "
                  f"out of place against our order "
                  f"{it['boxes_reordered']} (the postprocessor sort moved "
                  f"{it['reordered_by_postprocessor_sort']}, the rules "
                  f"permuted {rules}); reading order {order}")
        return {
            "name": self.name,
            "model": getattr(self, "full_name",
                              "docling-layout-heron (RT-DETRv2 R50)"),
            "architecture": getattr(self, "architecture", "RT-DETRv2 R50"),
            "weights_dir": self.dir,
            "sha256_weights": _sha256(self.onnx),
            "onnxruntime": self.ort_version,
            "providers": self.providers,
            "input": {"height": self.target_h, "width": self.target_w,
                     "pil_filter": self.interp_pil,
                     "cv2_filter": self.interp, "padding": self.do_pad,
                     "input_uint8": self.uint8_input,
                     "divide_by_255": self.do_rescale,
                     "normalization": self.do_normalize},
            # The weights have no native threshold -- a VALUE, not an omission.
            "native_threshold": None,
            "thresholds_by_class": self.thresholds(),
            # Not an empty list: the `threshold_drift` guard says the build has
            # NO native threshold and that ours acts. An empty field beside it
            # read as "no drift", the fingerprint contradicting its own guard.
            "threshold_drift": self.threshold_drift(),
            "label_vocabulary": self.labels,
            "label_map": self.label_map(),
            "prompts": {},
            # The model gives no reading order at all. Declared as a value, so
            # that "order 100%" by it cannot be taken for the model's merit.
            "reading_order": None,
            # The vendor pipeline is named at `off` too -- as a VALUE, not an
            # omission. An empty place would read as "not looked at", and this
            # is "looked at and switched off": without it two runs 5826 boxes
            # apart would differ in the fingerprint by one line of the knob
            # registry.
            "docling_pipeline": (self._pipe.fingerprint() if self._pipe else {
                "mode": "off",
                "what_is_it": ("the vendor postprocessing and docling's "
                            "reading-order rules; switched off -- the model "
                            "boxes go as they are, the order is ours"),
                "docling_version": None,
                "sha256_vendor_files": {},
                "postprocess_options": None,
                "label_map_to_docling": {},
                "summary": None}),
        }

    def read(self, image_path: str, index: int, dpi: float) -> Page:
        import cv2
        import numpy as np

        img = cv2.imread(image_path)
        if img is None:
            raise RuntimeError(f"the page raster does not read: {image_path}")
        h, w = img.shape[:2]
        rz = cv2.resize(img, (self.target_w, self.target_h),
                        interpolation=self.interp)
        x = rz[:, :, ::-1]                     # BGR -> RGB
        if self.uint8_input:
            x = np.ascontiguousarray(x.transpose(2, 0, 1)[None].astype(np.uint8))
        else:
            x = x.astype(np.float32)
            if self.do_rescale:
                x /= 255.0
            x = np.ascontiguousarray(x.transpose(2, 0, 1)[None])
        labels, boxes, scores = self.sess.run(
            None, {"images": x,
                   # (WIDTH, HEIGHT), not the other way round. Checked on a
                   # 1012x1466 sheet: reversed, the running foot went to
                   # x=1269, past the right edge of the sheet -- and the metric
                   # honestly gave zero matches out of a hundred and ten. The
                   # zero was about our axis order, not about the model.
                   "orig_target_sizes": np.array([[w, h]], np.int64)})
        labels, boxes, scores = labels[0], boxes[0], scores[0]

        thr = self.thresholds()
        kept, rejected = [], {}
        for cid, box, sc in zip(labels, boxes, scores):
            cid, sc = int(cid), float(sc)
            if not 0 <= cid < len(self.labels):
                raise RuntimeError(
                    f"the model returned class {cid}, the vocabulary knows "
                    f"{len(self.labels)}: an invented label is worse than a "
                    f"refusal.")
            lab = self.labels[cid]
            if sc < thr[lab]:
                if sc > rejected.get(lab, 0.0):
                    rejected[lab] = sc
                continue
            kept.append((lab, sc, [float(v) for v in box]))
        # The model gives no order, so it is ours, and it lives in `order.py`.
        kept = self._our_order(kept, w, h, index)
        blocks = [Block(block_id=i, box=tuple(b), label=lab, score=sc, order=i)
                  for i, (lab, sc, b) in enumerate(kept)]
        # The pipeline runs AFTER our sort and numbering, not before: the box
        # number is `Cluster.id`, by which the vendor stitches children to
        # their wrapper (see `_our_order`).
        blocks, pipe_meta = self._run_pipeline(blocks, w, h, index)
        return Page(
            index=index, width=w, height=h, dpi=dpi, blocks=blocks,
            raw={"output_rows": int(len(scores)),
                 "all_rows": [[float(c), float(s), *[float(v) for v in b]]
                                for c, b, s in zip(labels, boxes, scores)]},
            meta={"detector": self.name, "raster": image_path,
                  # This number is the MODEL's: how many boxes it gave above
                  # the threshold. How many remain after the vendor is said by
                  # "docling pipeline" -> "boxes after"; not to be confused.
                  "boxes_accepted": len(kept),
                  "rank_ties": 0,
                  # THE PLACE IN THE DICT IS NOT COSMETIC: the reading order
                  # stands where it stood before the pipeline, so at `off` the
                  # page comes out BYTE FOR BYTE as before. Otherwise the check
                  # "the knob is off, nothing changed" would stumble over the
                  # order of json keys instead of over the boxes.
                  **pipe_meta,
                  "best_rejected_by_class": rejected})


DEFAULT_LABELS = (
    "caption", "footnote", "formula", "list_item", "page_footer",
    "page_header", "picture", "section_header", "table", "text", "title",
    "document_index", "code", "checkbox_selected", "checkbox_unselected",
    "form", "key_value_region")


class DoclingEgret(DoclingHeron):
    """docling egret-medium: **D-FINE**, the third architecture on the bench.

    It differs from heron not in the weights but in the OUTPUT: this graph
    gives RAW logits and boxes in normalised cxcywh, not finished triples.
    Decoding them is part of D-FINE's own inference (sigmoid, picking the best
    queries, converting to corners), not our postprocessing: we move and merge
    no boxes, we only read what the graph left unread.
    """
    name = "docling-egret"
    policy_name = "Docling-egret"
    architecture = "D-FINE"

    def __init__(self, model_dir: str | None = None):
        self.full_name = "docling-layout-egret-medium (D-FINE)"
        super().__init__(model_dir or os.path.join(MODELS, "docling-egret_onnx"))
        names = [i.name for i in self.sess.get_inputs()]
        if names != ["pixel_values"]:
            raise WeightsMissing(
                f"graph input {names}, ['pixel_values'] was expected: "
                f"parsing at random means feeding the model the wrong "
                f"thing.")

    def read(self, image_path: str, index: int, dpi: float) -> Page:
        import cv2
        import numpy as np

        img = cv2.imread(image_path)
        if img is None:
            raise RuntimeError(f"the page raster does not read: {image_path}")
        h, w = img.shape[:2]
        rz = cv2.resize(img, (self.target_w, self.target_h),
                        interpolation=self.interp)
        x = rz[:, :, ::-1].astype(np.float32)
        if self.do_rescale:
            x /= 255.0
        x = np.ascontiguousarray(x.transpose(2, 0, 1)[None])
        logits, boxes = self.sess.run(None, {"pixel_values": x})
        logits, boxes = logits[0], boxes[0]          # [Q, C], [Q, 4] cxcywh
        prob = 1.0 / (1.0 + np.exp(-logits))          # focal loss -> sigmoid
        nq, nc = prob.shape
        if nc != len(self.labels):
            raise RuntimeError(
                f"the graph gave {nc} classes, the vocabulary knows "
                f"{len(self.labels)}: an invented label is worse than a "
                f"refusal.")
        # THE SELECTION FOLLOWS D-FINE'S OWN RULE, NOT argmax over classes
        # ("one query, one label"). No model of the DETR family finishes
        # reading itself that way: sigmoid, topk over the FLATTENED Q*C, label
        # = i % C, query = i // C. The same piece lies verbatim in the
        # postprocessing of RT-DETR and PP-DocLayoutV2 (`num_top_queries =
        # logits.shape[1]`), and the heron graph finishes reading itself by
        # exactly it: 300 rows per page, the same box arriving with several
        # labels -- up to 14 on atlas[0]; a CLASS never repeats inside one box
        # (0 groups of 13964), so a group is one query, not two findings.
        # HOW THE RULES DIVERGED, both decodings counted over the same rows: on
        # raw heron output the graph rule gives 1797 boxes and argmax 1488,
        # diverging on 22 pages of 93; on egret over 24 pages of six benches at
        # threshold 0.5 argmax gives 470 and the D-FINE rule 529, diverging on
        # 6 pages, and all 59 added are a SECOND label on an already accepted
        # box (54 of them List-item next to Text), with not one new geometry.
        # While the rules differed, comparing heron with egret measured our
        # decodings alongside the architectures. The topk length is NOT our
        # knob and not a threshold: it is Q, as many rows as the graph would
        # give had it been exported together with its postprocessing (in the
        # weights `num_queries = 300`).
        flat = prob.reshape(-1)
        top = np.argsort(-flat, kind="stable")[:nq]

        thr = self.thresholds()
        # How many rows ABOVE THEIR OWN THRESHOLD the topk itself cut off. The
        # cut is part of the model's rule, not our correction, but it must not
        # be passed over in silence: the D-FINE rule does not only add labels,
        # it also cuts, which argmax could never do. LAYOUT_SCORE_THRESHOLD is
        # a knob, and lowered it makes the cut bite. Measured over 24 pages of
        # six benches: at 0.5 and 0.3 ZERO was cut (the 300th value of the
        # sweep does not rise above 0.142), at 0.1 -- 206 rows on katalog[2],
        # where the page hits the ceiling exactly: 300 accepted = the topk
        # length. "Extra labels" says nothing about that loss. The zero here is
        # counted on EVERY page and means "topk cut nothing".
        thr_row = np.array([thr[lab] for lab in self.labels], np.float32)
        inside = np.zeros(nq * nc, bool)
        inside[top] = True
        cut = int(((prob >= thr_row[None, :]).reshape(-1) & ~inside).sum())

        kept, rejected = [], {}
        for idx in top:
            q, cid = int(idx) // nc, int(idx) % nc
            s = float(flat[idx])
            lab = self.labels[cid]
            if s < thr[lab]:
                if s > rejected.get(lab, 0.0):
                    rejected[lab] = s
                continue
            cx, cy, bw, bh = (float(v) for v in boxes[q])
            kept.append((lab, s, [(cx - bw / 2) * w, (cy - bh / 2) * h,
                                  (cx + bw / 2) * w, (cy + bh / 2) * h]))
        kept = self._our_order(kept, w, h, index)
        blocks = [Block(block_id=i, box=tuple(b), label=lab, score=s, order=i)
                  for i, (lab, s, b) in enumerate(kept)]
        # Coincident geometry is counted BEFORE the pipeline: it is a property
        # of the model's answer, while the one that suppresses such pairs is
        # the vendor (IoU > 0.8). Counted after, the number would speak of the
        # postprocessing while being called the selection rule of D-FINE.
        geom = [tuple(b) for _, _, b in kept]
        blocks, pipe_meta = self._run_pipeline(blocks, w, h, index)
        return Page(
            index=index, width=w, height=h, dpi=dpi, blocks=blocks,
            # The graph's answer WHOLE, before our selection. Keeping one class
            # and one sigmoid per query would put something already decoded
            # into the evidence: a threshold cannot be lowered for one class
            # without knowing its sigmoid on the queries where a neighbour won.
            # Measured on katalog[1]: sweeping down to 0.3 over the old raw
            # gave 11 boxes of 14, down to 0.2 -- 17 of 21; three and four
            # boxes were not "below the threshold" but invisible by the
            # construction of the evidence.
            raw={"output_rows": int(nq),
                 "class_count": int(nc),
                 "logits": [[float(v) for v in r] for r in logits],
                 "boxes": [[float(v) for v in r] for r in boxes],
                 "how_to_read_logits": "sigmoid per channel (focal loss)",
                 "raw_row_coords": "cxcywh, normalised"},
            meta={"detector": self.name, "raster": image_path,
                  "boxes_accepted": len(kept), "rank_ties": 0,
                  # See heron: the place of the key keeps the byte-for-byte
                  # match when the knob is off.
                  **pipe_meta,
                  # The selection rule as a value, not a word, and beside it a
                  # number showing it really worked: the old argmax cannot
                  # produce extra labels by construction, so a zero here means
                  # "the rules agreed on this page", not "the rule sat idle".
                  "selection_rule": f"topk {nq} over the flattened Q*C, "
                                    f"label = i % {nc} (as in D-FINE/RT-DETR)",
                  "extra_labels_on_shared_boxes":
                      len(geom) - len(set(geom)),
                  "rows_above_threshold_outside_topk": cut,
                  # CAREFUL: this field changed meaning with the rule. It was
                  # "the best rejected among the argmax winners", it is now
                  # "the best rejected among the topk rows". A class missing
                  # from the dict reads as "did not make the topk", NOT as
                  # "the model has no such class". Coverage grew: 4-8 classes
                  # per page before, 4-16 now (24 pages of six benches, 0.5).
                  "best_rejected_by_class": rejected})

