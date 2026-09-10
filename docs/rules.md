# The rules, and where each is enforced

Each rule is one sentence, one reason, and the symbols that enforce it,
written `path:symbol`. `tests/contract/test_docs.py` checks that every symbol
named here exists in the file named.

**Nobody repairs the model.** No merging of boxes, no cutting across the
gutter, no re-asking, no thresholds tuned by us. A patch does not improve the
book; it hides the defect from the measurement.
`src/booksmith/processing/read/transports/openai_http.py:Http.send` never
repeats a request that got an answer.
`src/booksmith/processing/read/driver.py:_sniff` observes what kind an
answer looks like and decides nothing.
`src/booksmith/core/raster.py:cut` refuses a negative margin rather than
shrinking a box.
`src/booksmith/processing/layout/adapters/docling.py:DoclingHeron` runs the
vendor's own post-processing unedited, and only when the knob says so.

**What was recognised is untouchable.** Everything observed lives beside the
block and is tied to it by anchor; nothing is appended to the model's text.
`src/booksmith/processing/read/__init__.py:Said` holds the model's bytes;
error and finish are separate fields.
`src/booksmith/processing/assemble/apply.py:put_into` marks the wrapper, not
the content.
`src/booksmith/datasets/make/subset.py:_carry_meta` refuses to overwrite a
truth field.

**A metric must be able to fail.** Feed it deliberately broken input and
watch the number fall before believing it.
`src/booksmith/datasets/metrics/base.py:Metric.probes` is the contract; every
registered metric has a `probes/<name>.py` module beside it, and
`src/booksmith/datasets/metrics/mutate.py` holds the shared spoilers.

**Log the quantity, not the word done.** Unfinished work is found by
comparing a count with what was expected.
`src/booksmith/processing/read/driver.py:report` prints the tally always.
`src/booksmith/processing/layout/detect.py:run` prints boxes per page.
`src/booksmith/core/log.py:log` carries the numbers as fields beside the
text, so a sink counts without parsing a line.

**Zero from a check and zero from not understanding are different zeros.**
A counter that can mean both must say which.
`src/booksmith/core/page.py:load_pages` raises `Unmeasurable` on a directory
with no pages rather than returning an empty result.
`src/booksmith/datasets/metrics/base.py:Scalar` cannot be built null without
a reason.
`src/booksmith/core/errors.py:Unmeasurable` exits with a different code from
`src/booksmith/core/errors.py:Refusal`.

**A knob is declared in the registry and read through the job.** A knob
read past the registry does not reach the snapshot, and the run becomes
silently unrepeatable; a value read past the job cannot differ between two
jobs in one process.
`src/booksmith/core/knobs.py:knob` raises on an undeclared name and takes
the value from `src/booksmith/core/job.py:current`.
`src/booksmith/core/job.py:Job.active` refuses a setting no knob is
declared for.
`src/booksmith/core/knobs.py:snapshot_with_readers` writes every knob the
run read into `run.json`.
`src/booksmith/core/stamp.py:identity` hashes exactly those values.

**Numbers may be flagged, never restored.** Words and structure may be
repaired; a damaged cell is marked less often than an ordinary one, and a
shifted row is invisible by construction.
`src/booksmith/datasets/metrics/reading.py:ReadingMetric` flags a chart
answered as a table of numbers; the restoring half is enforced when corrections
arrive as derived runs.

**One run per label, and a different identity refuses.** Two experiments
under one directory read as one run resumed.
`src/booksmith/core/book.py:guard_identity` refuses a different identity, an
absent one, and a partial run over a whole one.
`src/booksmith/core/book.py:safe_label` refuses a label that is not a
directory name rather than sanitising it.

**Imports go one way.** The layer table in `docs/architecture.md`.
`src/booksmith/core/layers.py:MAY_IMPORT` declares it and
`tests/contract/test_layers.py` walks every import against it.

**The same book, by hash.** A measurement names the scan it was taken on.
`src/booksmith/datasets/bench.py:same_book` compares the manifest's hash
with the run's, and says aloud when it could not check.

**Identity is what a model serves, never where it runs.** A served run of a
model and an in-process run of it under one setting are one experiment; the
address and the adapter that reached it are not in the hash.
`src/booksmith/core/served.py:identity_of` hashes the describe's fingerprint
with the knobs read on both sides, and
`src/booksmith/core/stamp.py:KNOBS_NOT_IDENTITY` keeps the endpoints and the
adapter's name out.

**A store reaches only itself.** A user's job reads and writes under the
user's store, by real path, outputs included; the admin's store is the data
home. `src/booksmith/service.py:_inside` refuses every path a service
function is given that lies outside, and the web's routes take names, never
paths, so there is nothing to refuse.
