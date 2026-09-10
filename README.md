# booksmith

Scans of technical books become a document: a layout model draws the boxes,
a vision-language model reads them, and every run is measured against truth
where truth exists. `ARCHITECTURE.md` is the map.

```
schema/    the contracts, as data
images/    one directory per image: backend, metrics, fleet, layout, vlm, datasets, ui
infra/     compose, the proxy, CI
bench/     the tracked truth of the real benches
```

Run everything: `docker compose -f infra/compose.yml up`. The API is at
`:8080/api`; the UI is not built yet.

Develop: `uv sync --all-packages --group dev`, then in any image directory
`uv run pytest`; `uv run ruff check images`.
