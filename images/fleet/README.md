# fleet

The model manager. The registry names each model; a placement is a running
copy of one; a lease is a job's hold on a placement. The backend asks for a
model by name and gets an endpoint and a key; where the model runs is the
fleet's business alone.

Run: `python -m fleet`. Environment: `BOOKSMITH_HOME` (the data volume),
`PORT`, `FLEET_KEY` (the bearer key the backend presents; unset, no key),
`FLEET_SWEEP_S` (how often idle and overdue placements are stopped),
`FLEET_DOCKER_NETWORK` (the network model containers join; unset, they
publish a loopback port), `VAST_API_KEY` (or the SDK's key file,
`~/.config/vastai/vast_api_key`). Tests: `pytest`; the docker test runs when
a daemon answers, the vast account test only with `-m vast`.

| route | what |
|---|---|
| `GET /models`, `PUT /models` | the registry: `{name: {kind, endpoint \| image + provider, knobs, api_key, env, port, idle_s, budget_usd, gpu, gpu_name, max_dph, disk_gb, min_reliability, min_down_mbps, cuda_min}}` |
| `POST /leases {model, job, wait_s}` | an endpoint, a key and a lease (200), or `starting` (202) when the placement is not ready within `wait_s`; the caller asks again |
| `POST /leases/renew {job}`, `POST /leases/release {job}`, `GET /leases` | a job's hold on its placements |
| `GET /placements`, `DELETE /placements/{id}` | what is running, and a stop by hand |
| `POST /reconcile`, `POST /sweep`, `GET /ledger`, `GET /health` | adopt or destroy what the providers hold; stop idle and overdue placements; what each placement cost |

Providers: `docker` runs the image on this machine's daemon under the label
`bs.owner=fleet` (`gpu: true` adds the card); `vast` rents the cheapest
offer matching `gpu_name`, `max_dph`, `disk_gb`, `min_reliability`,
`min_down_mbps` and `cuda_min`, runs the image there with its port
published, and reaches it by the instance's public address. That path is
plain HTTP over the internet with the placement's key: the key and every
page cross in the clear. A placement with no live lease past `idle_s` is
stopped; one past `budget_usd` (a bound per placement, not on the total) is
destroyed whatever is running; one that died is dropped; one the table does
not know is destroyed at reconcile, which runs at start and every tenth
sweep. Every model container gets `BOOKSMITH_IDLE_S`, twice `idle_s` plus
ten minutes: with no request that long it exits on its own, and on vast
destroys its instance, so a fleet that is down does not bill forever. The
ledger holds what each placement cost.
