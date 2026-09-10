import os

import uvicorn

from metrics.app import create_app

uvicorn.run(create_app(), host="0.0.0.0", port=int(os.environ.get("PORT") or 8000))
