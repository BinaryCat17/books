# fleet

The model manager. The registry names each model; a placement is a running
copy of one; a lease is a job's hold on a placement. The backend asks for a
model by name and gets an endpoint and a key; where the model runs is the
fleet's business alone.

Run: `python -m fleet`. Environment: `BOOKSMITH_HOME` (the data volume),
`PORT`, `FLEET_SWEEP_S` (how often idle and overdue placements are
stopped), `FLEET_DOCKER_NETWORK` (the network model containers join; unset,
they publish a loopback port), the vast key where the SDK reads it.
Tests: `pytest`; `-m docker` and `-m vast` need a daemon and an account.

| route | what |
|---|---|
| `GET /models`, `PUT /models` | the registry: `{name: {kind, endpoint \| image + provider, knobs, api_key, env, gpu, port, idle_s, budget_usd}}` |
| `POST /leases {model, job}` | an endpoint, a key and a lease; a placement is started if none is ready |
| `POST /leases/renew {job}`, `POST /leases/release {job}`, `GET /leases` | a job's hold on its placements |
| `GET /placements`, `DELETE /placements/{id}` | what is running, and a stop by hand |
| `POST /reconcile`, `POST /sweep`, `GET /ledger`, `GET /health` | adopt or destroy what the providers hold; stop idle and overdue placements; what each placement cost |

Providers: `docker` runs the image on this machine's daemon under the label
`bs.owner=fleet`; `vast` rents a card, runs the image there with its port
published, and reaches it by the instance's public address with the
placement's key. A placement with no live lease past `idle_s` is stopped; one
past its budget is destroyed whatever is running; one the table does not
know is destroyed at reconcile.
