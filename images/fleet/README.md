# fleet

The model manager. Today a placeholder: `GET /placements` answers an empty
list and `GET /health` says it is up. The registry stays in the backend
(`/api/models`) until this image owns placements and leases over the docker
and vast providers, whose code (`box`, `vast`, `runner`, `ledger`) is here
from the old rental.

Run: `python -m fleet` with `BOOKSMITH_HOME`. Tests: `pytest`.
