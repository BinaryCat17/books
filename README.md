# books

Scans of technical books into HTML.

Two levels. The first walks the whole scan and returns contours: boxes,
labels, reading order, and not one character of text. It runs on the CPU and
costs nothing. The second takes each block in isolation and turns it into a
fragment of HTML with a vision-language model on a rented card. It is the only
step that spends money, and every substitution it makes is journaled and can
be undone.

Benches and instruments came before models. A synthetic bench with exact
truth, a golden bench of real pages marked up by librarians, and for every
metric a battery of deliberately spoiled input that must make the number
fall. What each model found is in `METRICS.md`, rendered from the records
that measured it.

## Install

```bash
uv sync --extra detect --extra docling --group dev
.venv/bin/vastai set api-key <KEY>          # only for renting
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_vast -N ''
```

Secrets go into `.env` at the root, not versioned; the template is
`.env.example`.

## The five commands

```bash
books doctor                        # check everything before money moves
books detect bench/slovar           # level one, into detect/<model>/
books read bench/slovar/detect/PP-DocLayoutV2   # level two, paid
books html <read dir>               # the book as HTML, with a swap journal
books bench all bench/slovar        # every applicable metric on one run
```

Everything else, with flags: `docs/commands.md`.

## Where to read next

- `docs/architecture.md`: the two levels, the three layers, the book
  directory, the page format, and where this is going.
- `docs/rules.md`: the rules that are not negotiable.
- `docs/extending.md`: how to add a detector, a reader, a metric, a bench.
- `docs/models.md`: every model measured, and the verdict.
- `CLAUDE.md`: the map of the code.

## Tests

```bash
pytest
```
