"""Every measured number in this project, as one generated document.

WHY GENERATED AND NEVER EDITED. The measurements used to live as prose in five
documents, and `booksmith.tree.figures` counts what that cost: figures stated
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

from booksmith.core import config
from booksmith.core.errors import Refusal
from booksmith.datasets import table

RESULTS = os.path.join(config.ROOT, "results")
OUT = os.path.join(config.ROOT, "METRICS.md")

# The few a reader wants first. Everything else is in the per-bench tables
# below them; nothing is hidden, only ordered.
# WHICH WAY IS BETTER, PER SCALAR. The legend used to say "shares are 0..1 and
# higher is better except excess_jumps_per_page" -- and `label_errors`,
# `role_errors`, `excess_jumps`, `transitions` and the snapshot counts are not
# shares at all, and higher is worse for most. Read by that legend, V3's 442
# label errors BEAT V2's 207: the very inversion the denominators were added
# to fix, reintroduced one file over because the VALUE column is still the raw
# count. A scalar not named here is a share where higher is better.
LOWER_IS_BETTER = (
    "label_errors", "role_errors", "excess_jumps", "excess_jumps_per_page",
    "objects_torn", "objects_left_as_text", "objects_with_company",
    "ink_outside_boxes", "snapshot/missing", "snapshot/empty",
)
# Counts that are neither better nor worse -- they describe the bench or the
# run, and ranking models by them is meaningless.
NEITHER = ("transitions", "pages_with_columns", "values_present",
           "fingerprint_verified")

HEADLINE = (
    ("contour", "artefacts_found", "tables and pictures found"),
    ("contour", "text_furniture_found", "text and furniture found"),
    ("contour", "assembly_order", "reading order of the assembled book"),
    ("fitness", "ink_under_boxes", "ink that lands inside some box"),
    ("fitness", "object_ink_preserved", "ink of the objects that survives"),
    ("assembly", "excess_jumps_per_page", "excess column jumps per page"),
)


def _cells():
    """(bench, run) -> {metric: record dict}, and the commits they came from."""
    out, commits, when = {}, set(), set()
    for name in sorted(os.listdir(RESULTS)) if os.path.isdir(RESULTS) else []:
        if not name.endswith(".json") or "-only-" in name:
            continue
        d = table.read_file(os.path.join(RESULTS, name))
        commits.add(d["commit"])
        when.add(d["when"])
        for rec in d["records"]:
            out.setdefault((rec["bench"], rec["run"]), {})[rec["metric"]] = rec
    return out, commits, when


def _arrow(scalar: str) -> str:
    """Which way is better, as a property of the scalar."""
    if scalar in NEITHER:
        return "="
    return "↓" if scalar in LOWER_IS_BETTER else "↑"


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
        return "·"
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
    cells, commits, when = _cells()
    if not cells:
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
    if len(commits) > 1:
        raise Refusal(
            f"the results come from {len(commits)} different trees "
            f"({', '.join(sorted(commits))}). A table whose cells were "
            f"computed by different code is not a comparison. Re-run the "
            f"sweep: `python3 tools/sweep.py --apply --again`.")
    benches = sorted({b for b, _ in cells})
    runs = sorted({r for _, r in cells})
    commit = next(iter(commits))

    L = [f"# What this project measures, and what it measured",
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
         "lower, **=** neither (it describes the bench or the run, and "
         "ranking models by it means nothing). Two cells that cannot be "
         "compared are never put in one column without saying so.",
         "",
         "`—` is a value that does not exist, and the reason is under its "
         "table. `·` is a metric that does not apply to that pair. **`?` is "
         "NOT MEASURED** -- the run was never made or never scored, and it is "
         "not a result.",
         ""]

    # ---- what is NOT here -------------------------------------------------
    read_runs = [(b, r) for (b, r), m in cells.items() if "text" in m]
    L += ["## What is not in this table", "",
          "**The reading.** Level two runs a VLM on a rented card and costs "
          "money; nothing here rents anything. "
          + (f"{len(read_runs)} reading runs are measured below."
             if read_runs else
             "No reading run has been measured against a truth yet, so there "
             "is no reading row at all -- `docs/limits.md` says in three "
             "reasons why, before any money is spent."),
          "",
          "**Anything a bench cannot support.** A metric whose prerequisites "
          "a bench does not meet is absent, not zero, and the reason is "
          "printed under the table it would have been in -- taken from the "
          "record, not typed here. A sentence typed into this document about "
          "a particular bench was wrong for a day while the dash two lines "
          "below it was right; that is what a generated file is for.",
          ""]

    # ---- the headline -----------------------------------------------------
    L += ["## The short answer", ""]
    for metric, scalar, what in HEADLINE:
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
                L += [f"  not measured on this bench: "
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
