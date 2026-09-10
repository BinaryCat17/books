import os

import uvicorn

from layout import job, knobs, serve, settings
from layout.log import log

with job.Job(settings={k: v for k, v in os.environ.items() if k in knobs.names()}).active():
    det = serve.adapter(knobs.knob("LAYOUT_ADAPTER"))
    kind = os.environ.get("BOOKSMITH_SERVE_KIND") or "layout"
    kinds = tuple(k for k in (os.environ.get("BOOKSMITH_SERVE_KINDS") or "").split(",") if k)
    svc = serve.Service(det, kind, kinds, os.environ.get("BOOKSMITH_SERVE_KEY") or None)
    log(
        f"serving {svc.describe.kind} {svc.describe.label}: {len(svc.describe.classes)} labels, schema {settings.schema_dir()}"
    )
    uvicorn.run(serve.create_app(svc), host="0.0.0.0", port=int(os.environ.get("PORT") or 8000))
