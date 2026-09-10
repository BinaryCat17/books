# booksmith

Scans of technical books into HTML: a layout model draws the boxes, a
vision-language model reads them, and every run is measured against truth
where truth exists.

`ARCHITECTURE.md` is the map: the systems, their contracts, the catalog, the
six rules, the order of work. Each system's `README.md` says what it is, how
to run it and what its API is. Nothing else is documentation.

## Conventions

- One directory per system, flat. `formats/` is the only shared code.
- A commit message is one line, with a paragraph when the why is not obvious. History lives in git and nowhere else.
- No generated documents, no measurements in prose, no diaries.
- Tests live beside their system. The suite passes before a commit.
- After each step of the order of work, a sceptic review; its fixes land inside the step.

## Transition

Until the split lands, the code is still under `src/booksmith/` with its old
tests, docs and command line; `uv run pytest` runs the suite. The split
removes them, as `ARCHITECTURE.md` lists.
