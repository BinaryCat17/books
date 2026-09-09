"""Every measured number in this project, as one generated document.

WHY GENERATED AND NEVER EDITED. The measurements used to live as prose in five
documents, and the prose that held them is deleted; figures stated
in two documents at once, free to drift apart in silence. A number that is
rendered from the record that produced it cannot drift from it -- and when the
record is gone, so is the row, which is the honest outcome.

WHAT IT REFUSES TO DO. It will not put cells from two trees in one table. Each
`results/*.json` carries the commit that computed it, and a table whose
cells came from different code is not a comparison -- measured the hard way:
inside one hour a prerequisite was corrected, five models were measured after
it and one before, and the stale cell's twelve extra rows read as a difference
between MODELS.

EVERY VALUE CARRIES WHAT IT IS OVER. A bare share ranks models wrong, and this
project has the receipt: label errors printed as a count made the model with
239 matched pairs look twice as good as the one with 495. So a cell is
`value  n/of` and, where a metric declares coverage, `over` in its unit. A
missing value prints as the reason it is missing, never as a blank or a zero.

AND `excess_jumps` IS NOT ONE COLUMN. It counts jumps over the page's block
list, which is the MODEL's rank for a model that has one and OUR top-down rule
for a model that has none -- two quantities. The `order_rule` param says which,
and the table prints it beside the model rather than letting the reader assume.
"""
import collections
import os

from booksmith.core import config, stamp
from booksmith.core.errors import Refusal
from booksmith.datasets import table

RESULTS = os.path.join(config.ROOT, "results")
OUT = os.path.join(config.ROOT, "METRICS.md")
QUESTIONS = (
    ("How much of the book survived",
     "Ink, objects and blocks -- four populations with four denominators, "
     "which is why they are four rows and not an average. Read them with "
     "the box-shape guards below: a model that boxes the whole sheet takes "
     "100 % of the ink having found nothing."),
    ("Is the order right",
     "Where the truth marks reading order, agreement with it; where it does "
     "not -- and it is marked on no real page in this project -- how often "
     "the assembled order jumps between columns."),
    ("What failed, and how",
     "The derivatives: an artefact can be missed, cut, called text, or "
     "merged with its neighbour, and those four account for every one that "
     "did not arrive whole."),
)


def specs() -> dict:
    """Every published scalar, by name, as its metric declares it."""
    from booksmith.datasets.metrics import METRICS
    out = {}
    for m in METRICS:
        for sp in m.scalars:
            if sp.name in out:
                raise Refusal(f"scalar `{sp.name}` is declared by two metrics")
            out[sp.name] = sp
    return out


def headline() -> list:
    """(question, metric, scalar, gloss) for every scalar that headlines a question."""
    from booksmith.datasets.metrics import METRICS
    titles = [q for q, _ in QUESTIONS]
    out = []
    for q in titles:
        for m in METRICS:
            for sp in m.scalars:
                if sp.question == q:
                    out.append((q, m.name, sp.name, sp.gloss))
    return out




def _cells():
    """(bench, run) -> {metric: record dict}, the commits they came from, and
    THE RUNS OF ANOTHER LEVEL that were left out.

    This document is a cross-DETECTOR table: one row per model, one column
    per bench, and every number a property of the boxes that model drew. A
    level-two run's pages carry the boxes of whatever detector made them, so
    its ink and column-jump numbers describe that detector -- put in the
    model column under the reader's name, they read as the reader's work.
    Six detectors and one reader in one column is the "looks sensible and
    means nothing" case, and it was one `books bench all` away: the reader
    rendered as a seventh model row carrying `0.857` for boxes it never
    drew, with `?` in every other column.

    So a run of any level but `detect` is kept OUT and COUNTED, never
    silently dropped -- the count is printed under "What is not in this
    table", which is where a reader looks for what a number's absence means.
    """
    out, commits, when, other = {}, set(), set(), []
    for name in sorted(os.listdir(RESULTS)) if os.path.isdir(RESULTS) else []:
        if not name.endswith(".json") or "-only-" in name:
            continue
        d = table.read_file(os.path.join(RESULTS, name))
        # A file written before the field existed is `detect`, which every
        # one of them was.
        kind = d.get("kind") or "detect"
        commits.add(d["commit"])
        when.add(d["when"])
        if kind != "detect":
            # HELD OUT OF THE MODEL COLUMN, NOT OUT OF THE DOCUMENT. Its
            # numbers describe the detector whose boxes it inherited, so it
            # cannot stand beside six detectors as a seventh -- but it is
            # the only run that has READ anything, and the scalars about
            # reading have nowhere else to appear. It gets its own section
            # and the same commit rule: published means held to it.
            by = {}
            for rec in d["records"]:
                by[rec["metric"]] = rec
            other.append((kind, name, d["records"][0]["bench"] if d["records"]
                          else name, d["records"][0]["run"] if d["records"]
                          else "", by))
            continue
        for rec in d["records"]:
            out.setdefault((rec["bench"], rec["run"]), {})[rec["metric"]] = rec
    return out, commits, when, other


def _arrow(scalar: str) -> str:
    """Which way is better, from the metric's own declaration; refuses an undeclared name."""
    sp = specs().get(scalar)
    if sp is None:
        raise Refusal(
            f"scalar `{scalar}` declares no direction: add a Spec for it to "
            f"its metric's `scalars`.")
    return {"higher": "↑", "lower": "↓", "neither": "="}[sp.better]


def _num(v):
    if v is None:
        return None
    return f"{v:.3f}" if isinstance(v, float) else str(v)


def _cell(rec, scalar, measured=True):
    """One value with everything it is over, or the reason there is none.

    THREE ABSENCES, KEPT APART, because they are the project's own rule about
    two different zeros. `?` -- this pair was never measured, and nothing here
    is a result about it. `·` -- it was measured and this metric does not
    apply to it. `—` -- it applies, and the value does not exist, with the
    reason under the table. One dot used to mean the first two, under a legend
    claiming the second: a bench measured on two of six models read as a
    complete comparison of six.
    """
    if not measured:
        return "?"
    if rec is None:
        return "·"
    sc = (rec.get("scalars") or {}).get(scalar)
    if sc is None:
        # A FOURTH ABSENCE, AND IT WAS WEARING THE THIRD ONE'S MARK. The
        # metric RAN -- its record is right here -- and this scalar is not in
        # it, which can only mean the record was written before the scalar
        # existed. That is "not measured", `?`, and it read as `·`, "does not
        # apply to that pair", which is a claim about the bench. Six scalars
        # added and not yet swept published nine benches' worth of a
        # statement nobody made.
        return "?"
    v = _num(sc.get("value"))
    if v is None:
        return "—"
    out = v
    c = sc.get("count")
    if c:
        out += f" <sub>{c['n']}/{c['of']}</sub>"
    o = sc.get("over")
    if o and o["n"] != o["of"]:
        # PARTIAL COVERAGE ONLY, and it is the thing worth shouting: "45 of 49
        # blocks, counted over 6 of 130 pages" is a different claim from the
        # same share over all of them, and collapsing the two is how a number
        # measured on six pages was read as a number about a hundred and
        # thirty. Full coverage is the quiet case and stays quiet.
        out += f" <sub>over {o['n']}/{o['of']} {o.get('unit') or ''}</sub>"
    return out


def _why(rec, scalar):
    sc = ((rec or {}).get("scalars") or {}).get(scalar) or {}
    return sc.get("why") if sc.get("value") is None else None


def _table(rows, header):
    out = ["| " + " | ".join(header) + " |",
           "|" + "|".join("---" for _ in header) + "|"]
    for r in rows:
        out.append("| " + " | ".join(r) + " |")
    return out


def build(log=print) -> str:
    cells, commits, when, other_levels = _cells()
    if not cells:
        # TWO DIFFERENT EMPTIES, and the second is not "nothing measured".
        # Results exist, and every one of them is of a level this document
        # does not render -- telling the reader to measure would send them
        # to repeat work that is already on disk.
        if other_levels:
            raise Refusal(
                f"{RESULTS} holds {len(other_levels)} results and every one "
                f"is of another level ("
                + ", ".join(sorted({k for k, _ in other_levels})) +
                "). This document is a cross-detector table; a level-two "
                "run carries the boxes of whatever detector made its pages. "
                "Measure a detect run to have anything to render.")
        raise Refusal(
            f"no results in {RESULTS}. Measure first: `python3 "
            f"tools/sweep.py --apply` runs every model over every bench.")
    # AN UNCOMMITTED TREE IS ITS OWN ANSWER, and a clearer one than "two
    # different commits" -- the marker is the same sha with `+dirty tree`
    # after it, and the first edition printed both truncated to twelve
    # characters, so the refusal read "44553f64829c and 44553f64829c".
    # `stamp.commit()` returns None on a box with no git -- the rented card is
    # exactly that -- and `sorted` over None and a string raises a bare
    # TypeError three lines down. A result that cannot name its code is the
    # same trouble as a dirty one and is said so.
    if None in commits:
        raise Refusal(
            "some results record no commit at all: they were measured where "
            "git could not be asked (a rented machine has no repository). "
            "What produced them cannot be recovered, so they cannot be "
            "published beside numbers that can.")
    dirty = sorted(c for c in commits if c and "dirty" in c)
    if dirty:
        raise Refusal(
            f"{len(dirty)} of {len(commits)} results were measured against an "
            f"UNCOMMITTED tree ({dirty[0]}). What code produced them cannot "
            f"be recovered, so they cannot be published beside numbers that "
            f"can. Commit, then `python3 tools/sweep.py --apply --again`.")
    # AND THE COMMIT MUST STILL EXIST. A sha records what HEAD was while the
    # cells were counted, and history is rewritten afterwards often enough --
    # a squash, a rebase, an amend. Measured: all 54 results were stamped
    # against a `wip:` commit, the `wip:` commits were then folded into one
    # with `git reset --soft`, and every published number named a commit
    # `git log --all` no longer showed. Nothing above catches it: the stamp
    # was not None, not dirty, and all 54 agreed with each other -- they
    # agreed on a commit that was gone.
    #
    # `None` from `reachable` is "git cannot answer" -- no repository at all,
    # or a sha this clone has never seen -- and it is refused with the same
    # force as `False`, because both mean the code cannot be got back.
    unreachable = sorted(c for c in commits if stamp.reachable(c) is not True)
    if unreachable:
        raise Refusal(
            f"the results name a commit that is not in this history: "
            f"{unreachable[0]}. It was rewritten away (a squash, a rebase, an "
            f"amend) or belongs to another clone, so the code that produced "
            f"these numbers cannot be got back -- which is the one thing the "
            f"stamp is for. Re-measure: `python3 tools/sweep.py --apply "
            f"--metrics-only`.")
    if len(commits) > 1:
        raise Refusal(
            f"the results come from {len(commits)} different trees "
            f"({', '.join(sorted(commits))}). A table whose cells were "
            f"computed by different code is not a comparison. Re-run the "
            f"sweep: `python3 tools/sweep.py --apply --again`.")
    benches = sorted({b for b, _ in cells})
    runs = sorted({r for _, r in cells})
    commit = next(iter(commits))

    L = ["# What this project measures, and what it measured",
         "",
         "GENERATED -- do not edit. Every number here is rendered from the "
         "record that produced it (`results/*.json`), so it cannot "
         "drift from the run it describes. Remake it with:",
         "",
         "```",
         "python3 tools/sweep.py --apply      # measure",
         "books bench report                  # render this file",
         "```",
         "",
         f"All cells were computed at commit `{commit}`, "
         f"{'at ' + sorted(when)[0] if len(when) == 1 else 'between ' + sorted(when)[0] + ' and ' + sorted(when)[-1]}.",
         "",
         "Each cell is the value with the count behind it. Where a metric "
         "was counted over only PART of a bench, the cell says so; where it "
         "says nothing, it was counted over all of it.",
         "",
         "A scalar's name carries an arrow: **↑** better higher, **↓** better "
         "lower, **=** neither end is better. An `=` scalar either describes "
         "the bench or the run, so ranking models by it means nothing, or it "
         "is a GUARD -- read across models, but beside a ranked number "
         "rather than as one. `area_under_boxes` is a guard: a model that "
         "boxes the whole sheet takes 100 % of the ink with it, so a high "
         "share of ink is only worth what the area beside it says. Two "
         "cells that cannot be compared are never put in one column without "
         "saying so.",
         "",
         "`—` is a value that does not exist, and the reason is under its "
         "table. `·` is a metric that does not apply to that pair. **`?` is "
         "NOT MEASURED** -- the run was never made, or was scored before "
         "this row existed, and either way it is not a result. A whole row "
         "of `?` means the sweep has not been run since that number was "
         "added; it does not mean the benches cannot answer it.",
         ""]

    # ---- what is NOT here -------------------------------------------------
    read_runs = [(b, r) for (b, r), m in cells.items() if "text" in m]
    L += ["## What is not in this table", "",
          "**The reading.** Level two runs a VLM on a rented card and costs "
          "money; nothing here rents anything. "
          + (f"{len(read_runs)} reading runs are measured below."
             if read_runs else
             "No reading run has been measured against a truth yet, so there "
             "is no reading row at all -- `docs/architecture.md` says in three "
             "reasons why, before any money is spent."),
          "",
          "**Runs of another level.** This is a cross-DETECTOR table: every "
          "number is a property of the boxes a model drew. A level-two run "
          "carries the boxes of whatever detector made its pages, so its "
          "numbers describe that detector and not the reader named on the "
          "directory -- in the model column the reader would read as having "
          "earned them. "
          + (f"{len(other_levels)} such "
             + ("run is" if len(other_levels) == 1 else "runs are")
             + " kept out of the tables above and given a section of "
             + ("its" if len(other_levels) == 1 else "their")
             + " own at the end: "
             + ", ".join(f"`{b}` / `{r}` ({k})"
                         for k, _, b, r, _ in sorted(other_levels)) + "."
             if other_levels else
             "None has been measured yet; `books bench all <book> --kind "
             "read` writes one, under its own name, and it is counted here "
             "rather than dropped."),
          "",
          "**Anything a bench cannot support.** A metric whose prerequisites "
          "a bench does not meet is absent, not zero, and the reason is "
          "printed under the table it would have been in -- taken from the "
          "record, not typed here. A sentence typed into this document about "
          "a particular bench was wrong for a day while the dash two lines "
          "below it was right; that is what a generated file is for.",
          ""]

    # ---- the headline -----------------------------------------------------
    L += ["Three questions, and every row below answers one of them. Each "
          "keeps its own instrument and its own denominator -- nothing here "
          "is averaged into a score, because the two metrics that would be "
          "averaged each record in their own header that one combined number "
          "trades one defect for another.", ""]
    asked = None
    for question, metric, scalar, what in headline():
        if question != asked:
            asked = question
            L += [f"## {question}", "",
                  dict(QUESTIONS)[question], ""]
        L += [f"### {scalar} {_arrow(scalar)} — {what}", ""]
        rows = []
        for r in runs:
            row = [f"`{r}`"]
            for b in benches:
                row.append(_cell(cells.get((b, r), {}).get(metric), scalar,
                                 measured=(b, r) in cells))
            rows.append(row)
        L += _table(rows, ["model"] + benches)
        notes = sorted({_why(cells.get((b, r), {}).get(metric), scalar)
                        for b in benches for r in runs} - {None})
        if notes:
            L += [""] + [f"- a dash means: {n}" for n in notes]
        # WHOSE ORDER, BESIDE THE JUMPS. Excess jumps are counted over the
        # page's block list -- the MODEL's rank for a model that has one, and
        # OUR top-down rule for a model that has none. On the same boxes the
        # golden bench gives 2471 by our rule against 501 by the rank, five
        # times the spread a table shows, so two models under one heading with
        # two rules are not a comparison. This header claimed the table prints
        # it, and only the per-bench section did.
        if scalar.startswith("excess_jumps"):
            rules = collections.defaultdict(set)
            for r in runs:
                for b in benches:
                    par = ((cells.get((b, r), {}).get("assembly") or {})
                           .get("params") or {})
                    if par.get("order_rule"):
                        rules[par["order_rule"]].add(r)
            if rules:
                L += [""] + [f"- counted over `{k}`: "
                             + ", ".join(f"`{x}`" for x in sorted(v))
                             for k, v in sorted(rules.items())]
                if len(rules) > 1:
                    L += ["- **these are two different quantities**, and the "
                          "columns are not comparable across the two groups."]
        L += [""]

    # ---- the level-two runs, apart ----------------------------------------
    if other_levels:
        L += ["## What the reading runs measured", "",
              "A level-two run carries the boxes of whatever DETECTOR made "
              "its pages, so none of these numbers ranks the reader against "
              "the models above and none is in their tables. What it does "
              "carry is the only measurement of a book that has actually "
              "been read: how much of its ink leaves as text rather than as "
              "a picture of itself, and how much of the sheet was never "
              "information at all.", ""]
        for kind, _name, b, r, by in sorted(other_levels):
            L += [f"### {b} — {r} ({kind})", ""]
            rows = []
            for metric in sorted(by):
                for s, _sc in sorted((by[metric].get("scalars") or {}).items()):
                    rows.append([f"`{s}` {_arrow(s)}", metric,
                                 _cell(by[metric], s)])
            L += _table(rows, ["scalar", "metric", "value"]) + [""]
            notes = sorted({_why(by[m], s) for m in by
                            for s in (by[m].get("scalars") or {})} - {None})
            if notes:
                L += [f"- a dash: {n}" for n in notes] + [""]

    # ---- per bench, everything -------------------------------------------
    L += ["## Every scalar, bench by bench", ""]
    for b in benches:
        L += [f"### {b}", ""]
        here = {r: cells.get((b, r), {}) for r in runs}
        present = [r for r in runs if (b, r) in cells]
        if not present:
            L += ["Not measured.", ""]
            continue
        metrics = sorted({m for r in present for m in here[r]})
        for metric in metrics:
            names = sorted({s for r in present
                            for s in (here[r].get(metric) or {}).get("scalars", {})})
            rows = []
            for s in names:
                    rows.append([f"`{s}` {_arrow(s)}"]
                            + [_cell(here[r].get(metric), s,
                                     measured=(b, r) in cells) for r in runs])
            L += [f"**{metric}**", ""] + _table(rows, ["scalar"] + runs) + [""]
            # EVERY MODEL IS A COLUMN, measured or not. Dropping the unmeasured
            # ones from the header made a bench measured on two of six read as
            # a comparison of two.
            missing = [r for r in runs if r not in present]
            if missing:
                L += ["  not measured on this bench: "
                      + ", ".join(f"`{r}`" for r in missing), ""]
            notes = sorted({_why(here[r].get(metric), s)
                            for r in present for s in names} - {None})
            if notes:
                L += [f"- a dash: {n}" for n in notes] + [""]
            # THE PARAMS THE NUMBERS DEPEND ON, per model, because they are
            # not always the same one: `order_rule` differs between a model
            # with a reading rank and a model without.
            par = {r: (here[r].get(metric) or {}).get("params") or {}
                   for r in present}
            shared = {k: v for k, v in (par[present[0]] or {}).items()
                      if all(par[r].get(k) == v for r in present)}
            if shared:
                L += ["  params, the same for every model here: "
                      + ", ".join(f"`{k}={v}`" for k, v in sorted(shared.items())),
                      ""]
            for r in present:
                own = {k: v for k, v in par[r].items() if k not in shared}
                if own:
                    L += [f"  `{r}` differs: "
                          + ", ".join(f"`{k}={v}`" for k, v in sorted(own.items())),
                          ""]
    return "\n".join(L).rstrip("\n") + "\n"


def write(path: str = OUT, log=print) -> str:
    text = build(log=log)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    log(f"{path}: {len(text.splitlines())} lines")
    return path
