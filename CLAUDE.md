# booksmith

Scans of technical books into a document: a layout model draws the boxes, a
vision-language model reads them, every run is measured against truth where
truth exists. `ARCHITECTURE.md` is the map; each image's `README.md` says
what it is, how to run it and its API. Nothing else is documentation.

## Conventions

- One directory per image under `images/`, flat, self-contained. `schema/` is the only thing shared, and it is data.
- A commit message is one line, with a paragraph when the why is not obvious.
- No generated documents, no measurements in prose, no comments that restate the code.
- Tests live beside their image: `cd images/<name> && uv run pytest`. Each image's tests make their own small inputs.
- A test exercises behaviour. What is merely true of the tree -- a declared knob is read, an import is a dependency, a README cites what exists -- is `invariants.py`, one statement for every image, run like ruff.
- After each step of the order of work, a sceptic review; its fixes land inside the step.
