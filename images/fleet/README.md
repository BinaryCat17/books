# fleet

The model manager. Today: the registry, `GET|PUT /models`, one entry per
model: `{kind, endpoint | image + provider, knobs, key, idle_s, budget}`.
Next: placements and leases over the docker and vast providers, whose code
(`box`, `vast`, `runner`, `ledger`, `pricing`) is here from the old rental.

Run: `python -m fleet` with `BOOKSMITH_HOME`, the docker socket and the vast
key mounted. Tests: `pytest`.
