# 2026-09-07: step 2a, a bench you can open and a metric that returns a record

## What was built

`booksmith.datasets`, module 2's package, with the measurement bodies left
where they are for one more commit:

* `bench.py`: `Bench.open`, `Run.open`, `Run.bare`, `load_pages`,
  `same_book`, `trait_state`. One loader for the six that parsed the same
  directory; one identity check for the three that compared the book their
  own way; three trait states, and a trait the file does not name is "not
  said". `Run.open` requires the snapshot; `Run.bare` is the explicit way
  to score a page directory that honestly has none (truth against itself,
  a battery's spoiled copy) and the identity check then says NOT CHECKED
  in the very words the acceptance records lock.
* `metrics/base.py`: `Scalar` (value, over, why: a value of None without a
  reason is refused, a flag is refused), `Record` (scalars, params, detail),
  `Metric` (name, needs, run, report, battery), `applicable` by prerequisite
  only, `Probe` and `run_battery` with the counting rules of the three loops
  (the denominator is what was printed; a throwing probe is a failed probe
  with the exception in its line; "no data" is neither).
* `metrics/contour.py`, `metrics/text.py`, `metrics/fitness.py`: wrappers
  that call `metrics.compare`, `text.measure`, `fitness.measure` unchanged
  and read the scalars off the dict, so the four acceptance records lock the
  same dict they did. Thresholds ride in `params`. Fitness's shares are
  computed in the wrapper from the same counts the report divides.
* `table.py` and `books bench all <bench> [--run L] [--only a,b] [--json P]`:
  every applicable metric on one run, one table with a footnote per absent
  value, one JSON under `bench/results/`.

## What the first table said

On slovar's detect run: artefacts found 2 of 3, sense whole 2 of 3, text and
furniture 0.990 over 13 of 13 pages, model order and assembly order absent
because the truth says nothing about order on 13 of 13 pages (the synth
writes `order` but not `order_marked`, the audit's finding, fixed in 2c),
excess jumps 10.8 per page over 12 of 13, ink under boxes 0.976, one object
of three intact. The reading metric on a detect run says CER 1.000 over 520
of 520 with 515 unanswered, which is right: nothing has been read.

Two wrong lines on the first run, fixed before the commit: the reading
wrapper counted "answered" as blocks minus unanswered and printed 5 of 520
beside a reason that said none were answered (unmatched blocks are neither);
and it explained absent cell matches by "no table with a cell grid" when 227
cells existed and no table had been answered.

## The import rule under construction

`tree/imports.py` gained `UNPLACED`: the modules the plan has not placed
yet may be imported from anywhere until their step moves them, and a test
demands that every name in the tuple still stands at the top of the
package, so a placed module cannot stay exempt by forgetfulness. The tuple
must be empty after step 3c.

The docs-map test learnt nested subparsers: `books bench all` is a command
the map must name and `books score truth/` is not a ghost.
