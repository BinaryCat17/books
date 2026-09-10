# datasets

The bench builders, run on demand against the storage volume: a drawn bench
of the tree's own (`synth`), a bench out of the AnnoPage corpus
(`annopage`), the hard pages of several benches as one (`subset`).

```
docker compose run --rm datasets synth --book slovar --out /data/bench/slovar
python -m datasets annopage --root <corpus> --out <bench dir> [--split test] [--limit 600]
python -m datasets subset --books slovar,katalog --out <bench dir>
```

A bench is a book directory with `truth/`: `schema/page.schema.json`. Tests: `pytest`.
