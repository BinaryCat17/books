# booksmith

Scans of technical books become a document: a layout model draws the boxes,
a vision-language model reads them, and every run is measured against truth
where truth exists. `ARCHITECTURE.md` is the map.

```
schema/    the contracts, as data
images/    one directory per image: backend, metrics, fleet, layout, vlm, datasets, ui
infra/     the compose file
bench/     the tracked truth of the real benches
```

Run everything: `COMMIT=$(git rev-parse HEAD) BOOKSMITH_ADMIN=name:password docker compose -f infra/compose.yml up --build`.
`COMMIT` is stamped into the images and recorded by every run they produce; without it a run says it does not know.
The UI is at `:8080`, the API under `:8080/api`. Model images:
`--profile models build`.

Develop: `uv sync --all-packages --group dev`, then in any image directory
`uv run pytest`; `uv run ruff check images`; the UI: `cd images/ui && npm ci && npm run build`.
