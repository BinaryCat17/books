# books

Scans of technical books -> HTML. Plus a runner that rents a GPU for ANY job,
not only this one.

**The project is on a clean slate.** The previous pipeline is deleted -- 6.6k
lines out of 11.3k. Not because it failed, but because there was nothing to
show whether it worked: every quality figure was measured against the output
of another model (Mistral OCR), not against known text. The reference file is
gone and so are the run directories -- not one of those numbers can be
reproduced. What is void and what still stands: the preface of
`docs/ocr-notes.md`.

The map of code, commands and knobs lives in `CLAUDE.md`, and it lives there
ALONE -- as do the six rules. A second copy stood here and by 31 August had
drifted from the tree by eight modules and four commands, and the rules copy
had silently lost one of the six. A second copy diverges without a sound; the
same reason a knob's default lives in exactly one place.

## Where this is going

Two levels. Markdown is no longer the target, EPUB/FB2/PDF are not wanted --
the format builder is deleted.

**The first** returns **contours** -- boxes, labels, reading order -- and not
one character of text: a layout detector, not a recogniser, so HTML built from
contours alone is all pictures (`bench/slovar`: 568 pictures, 0 paragraphs). It
runs on the CPU and costs nothing. Measurements: `docs/contour-notes.md`.

**The second** (`books read`) takes each artefact **in isolation from its
neighbours** and turns it into a block of HTML, one at a time, so each can be
checked, rolled back and redone by another model without touching the book. It
is checked at home against a stub server (27 checks, not one cent), and on
2026-09-04 it read 436 real pages on a rented 4090 -- $0.545 over eight
rentals, two of them successful -- after which `books apply --from` put 412
replacements into one book. That 412 is NOT reproducible here: snapshot and
output live outside git, the commit in the snapshot reads "dirty tree". It
proves the tract works; it measures no quality.

## Five corruption batteries, and what each returns

Bench and metrics came **before** models: a synthetic bench with exact truth,
and a golden one of 600 real pages marked up by librarians. An instrument that
cannot fail cannot be trusted, so every metric carries a battery that feeds it
deliberately spoiled input. **None of the five returns zero on every input**,
and the input decides more than the battery does. Measured on this tree
2026-09-06:

| battery | zero uncaught on | red on |
|---|---|---|
| `books score --selfcheck` | 33 probes, all six synthetic books and `bench/annopage` | a ONE-PAGE directory: 2 false failures on a dense page (page shift, `TOUCH=1.01`), 10 on a sparse one |
| `books text --selfcheck` | 29 probes, 18-19 measured, `<book>/truth <book>/truth`, all six | `<book>/detect/pages`, all six: 2 to 5 uncaught. `bench/annopage`: **3**, not the 4 this file used to claim |
| `books fitness --selfcheck` | 21 probes, `spravochnik`, `atlas`, `katalog` | `slovar`, `matematika`, `zhurnal`: 1 uncaught each |
| `books replay --selfcheck` | nothing today | all seven benches -- while uncaught losses are 0 on every one |
| `tests/run.py --slow --selfcheck` | its figures are deliberately absent from this prose: the runner prints them on its last line | |

In four batteries of the five the red is at least in part the instrument
**reporting "nothing to break" as "did not catch"**, and each diagnosis is a
fact about the bench it ran on, so they live with the benches:
`bench/README.md`.

The honest kind of red is what the batteries are for: when the "anchor outside
the box" gate appeared in `text.py`, the probe beside it went on demanding the
old behaviour, and the battery returned 1 on all six synthetic benches -- the
instrument declaring itself broken exactly where it had got stricter.

## The job contract

The runner knows exactly three things: **input files, a command, and an output
directory**. There is nothing about PDFs or OCR in `remote/` -- otherwise the
next ML job would demand that renting be rewritten again.

```python
JobSpec(
    name="test25",
    image="ghcr.io/binarycat17/vast-base:<sha>",
    command="bash run.sh input.pdf outputs",
    inputs={"book.pdf": "input.pdf", "run.sh": "run.sh"},
    outputs="outputs",          # pulled back AS IT GOES, not at the end
    budget_usd=1.00,            # hard ceiling: reached means the machine dies
)
```

## Installing

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[detect]'            # detect -- onnxruntime, opencv
.venv/bin/vastai set api-key <KEY>              # console.vast.ai/account
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_vast -N ''
```

Secrets go into `.env` at the root (mode 600, not versioned), template in
`.env.example`. Fill them in yourself, in your own terminal.

**The commands money touches** are six, all of them described in `CLAUDE.md`:
`books doctor` (check everything BEFORE money starts moving), `offers`, `ls`,
`down <id>`, `reap`, `ledger`. Everything else -- parsing, benches, metrics --
runs locally on the CPU and costs nothing.

## How a machine is chosen

Not by price per hour. The ranking computes the **full cost of the run**:
delivery splits into two channels of very different capacity -- the image
through docker, the environment around it -- and above both sits **traffic,
whose inbound price is non-zero at EVERY offer, $0.4 to $29.3 per TB**. At the
worst offer on the market that is $0.23 against $0.35 of rent: 40% of the bill,
in a field that ranking by `dph_total` does not see.

## Money cannot leak

Destruction is duplicated because every single way of doing it has failed
once. Three defences are local:

1. `finally` -- on any exit, exceptions included;
2. SIGINT/SIGTERM trapping -- otherwise the process dies past `finally`;
3. a watchdog thread on the budget -- in case the main one hangs in ssh.

Plus a verification: after `destroy_instance` the instance list is requested
again -- a CLI used to be called here that **returned 0 even when it refused to
destroy**, and the script reported success while money ran. But all three share
one point of failure, a live local process: the operator's environment
restarted once and the instance kept billing while the job on it had died with
the ssh. So the fourth defence sits **on the rented machine itself**:

4. the dead man's watch. vast puts `CONTAINER_API_KEY` into the container -- a
   key with the right to destroy that instance. A loop from `onstart` watches
   the age of `/root/.alive`, which the operator touches every 30 seconds; if
   the touch stops for longer than 15 minutes the machine kills itself. With
   `--keep` the term rises to four hours: leaving on purpose is allowed,
   forgetting forever is not.

## The image and the environment

The image carries delivery tools only -- rsync, zstd, curl, uv, and the system
libraries for opencv and kernel compilation. No python, no CUDA, no torch: CUDA
arrives inside the torch wheels, uv installs python. **54 MB as measured
2026-08-19**, and that figure is stale: `procps` and `git` went into
`infra/base/Dockerfile` on 2026-09-05 (which puts git alone at 20 MB), and
there is no docker in this environment to re-measure with.

The design follows from one measurement -- **21+ minutes to come up through
docker against 3 minutes around it** (byte counts and the reason:
`docs/vast-notes.md`). So everything heavy is installed at start by
`provision.sh`: python, wheels, weights through `hf download`. Eighty seconds,
and idempotent -- on a warm machine (`--reuse`) it finishes in seconds.

Wheels come from `constraints.txt`, the pinned tree in full -- all 241
packages, not just the top level -- or dependency resolution happens on the
rented card and a fresh release of any transitive dependency drops the book
halfway. `requirements.in` is the input for regenerating it, command in its
header; the uv in the image must be the version that compiled it, or it will
not resolve.

The image tag is the short commit SHA, and that is not pedantry: vast rebuilds
any image with a layer of its own carrying ssh and caches the result on the
machine as `<image>_<tag>/ssh`. Under an unchanging `latest` the rebuild from
the old base stays there forever and fixes never arrive.

Everything else about vast.ai, rakes included: `docs/vast-notes.md`.
