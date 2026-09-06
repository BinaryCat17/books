# 2026-09-07: step 2b, first half -- the instruments can fail, and two metrics without truth

## Mutations for the new instruments

The battery reported thirty-eight checks running under no mutation after
step 2a: the bench, the record, the table, the import rule and the roots
had checks and nothing could break them. Eight attribute swaps now can: an
identity check that says "checked" without looking; a loader that takes any
json as a page; a trait state with two values; a scalar that accepts no
reason; applicability that ignores whether the truth has characters; a
battery loop that counts a throwing probe as "no data"; a selection that
bypasses applicability (a rebuilt line in `table.py`); records read back
without their scalars. For three of them the product code had to be
changed first, by the rule step 1 found: `bench` asks `page.load_pages`
through the module, the metrics registry stops re-exporting `applicable`,
and the table asks `base` for it, so that a swap on the owner reaches the
caller.

## The mutators, once

`datasets/metrics/mutate.py` holds the eight spoilers the contour battery
declared and the reading battery had copied; the contour battery imports
them under its old private names, so its line patches still land (anchors
73). The reading battery keeps its own `_shuffle_pages`: it returns None
on a one-page set where the contour's shifts anyway, and the difference is
what a probe of it measures.

## Two metrics that need no truth

`snapshot.py`: is the run's `run.json` complete, as scalars (values present
51 of 55 on slovar's detect run; missing 4; empty 14; fingerprint verified
0, because the adapter file's hash moved with the package). Its battery is
the knock-out loop factored out of `core.replay.selfcheck` as
`replay.knockout`, returning the omissions the check did not notice and
nothing else: `selfcheck` kept summing six troubles into one exit code,
which is right for a command and wrong for a battery, whose number is
about the check.

`assembly.py`: excess column jumps alone, with the parameters that decide
the count riding in `params`, so that `bench/real` and any book without
truth gets a number. Its battery is the three jump probes through the
shared `run_battery`: the first metric to use it, and its summary line has
the shape every battery will have after the fold.

The applicability test now expects `assembly` and `snapshot` on a bench
with pages and nothing else; the table on slovar gained thirteen lines and
the lock was regenerated with that reason.

## Second half: the three loops became one

The contour, reading and ink batteries each had their own loop over the
probes: the same four rules in three editions (a throwing probe is a failed
probe with the exception in its line; "no data" is neither caught nor
missed; the denominator is what was printed; the summary is a quantity).
They call `base.run_battery` now and end with `base.battery_summary`. The
contour battery's second group, whose outcomes are computed before the loop,
goes through the same loop as probes that return what they already know;
its third group, the three-pixel shift, keeps its own line because that
line has its own shape and the acceptance lock holds it.

What changed in print: nothing in the contour and reading reports (the
locks say `same`); in the ink report the mark column moved one character
left, to the width the other two always had, and a throwing probe would
now say "THE PROBE THREW" instead of "threw:" (none throws today). The
snapshot was regenerated with that reason; `--numbers` says not one number
moved. The line patches the mutation battery makes inside these loops all
still land (anchors 73).

Still owed from the plan's 2a and 2b: the overlay (`datasets/look.py`)
keeps its own identity check, which compares a PDF's hash against several
markups' snapshots at once and is not the bench-against-run check;
folding it is a design question for 3b, when runs get labels. The loaders
are one (`core.page.load_pages`) with two delegations that keep their
error class. What remains is 2c: the synthetic generator's split, and
`order_marked` in its truth.
