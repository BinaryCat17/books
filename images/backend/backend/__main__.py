import json
import os
import sys

from backend.app import create_app

if "--openapi" in sys.argv:
    print(json.dumps(create_app().openapi(), indent=1, sort_keys=True))
else:
    import uvicorn

    uvicorn.run(create_app(), host="0.0.0.0", port=int(os.environ.get("PORT") or 8000))
