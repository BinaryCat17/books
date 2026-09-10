# schema

The contracts between the images, as data. Every image validates what it
reads and writes against these in its own tests; nothing else is shared.

| file | what it describes |
|---|---|
| `page.schema.json` | a page: the model's boxes, or truth |
| `document.schema.json` | the book as data, assembled from a run; every export renders it |
| `describe.schema.json`, `health.schema.json`, `layout-request.schema.json` | the model protocol's payloads |
| `snapshot.schema.json` | `run.json` beside a run |
| `record.schema.json`, `catalog.schema.json` | a measurement, and the metrics a service publishes |
| `classes.json` | the class table every label maps onto |
| `openapi/model.yaml` | the model protocol |
| `openapi/backend.yaml`, `openapi/fleet.yaml`, `openapi/metrics.yaml` | each service's API, exported from the service |
