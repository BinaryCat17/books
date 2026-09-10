import os

from vlm import job, knobs, serve

with job.Job(settings={k: v for k, v in os.environ.items() if k in knobs.names()}).active():
    serve.main(int(os.environ.get("BOOKSMITH_PORT") or 8000), os.environ.get("BOOKSMITH_UPSTREAM") or "",
               os.environ.get("BOOKSMITH_SERVE_KEY") or None, os.environ.get("BOOKSMITH_LOG_DIR") or "/var/log")
