import shutil
import subprocess

import pytest

from fleet import registry
from fleet.docker import Docker
from fleet.placements import Fleet

SHIM = ("import json,os,sys;from http.server import BaseHTTPRequestHandler,HTTPServer\n"
        "class H(BaseHTTPRequestHandler):\n"
        " def log_message(s,*a):pass\n"
        " def do_GET(s):\n"
        "  ok=s.headers.get('Authorization')=='Bearer '+os.environ['BOOKSMITH_SERVE_KEY']\n"
        "  b=json.dumps({'ready':True,'label':'shim','requests':0}).encode() if ok else b'{}'\n"
        "  s.send_response(200 if ok else 401);s.send_header('Content-Length',str(len(b)));s.end_headers();s.wfile.write(b)\n"
        "HTTPServer(('0.0.0.0',int(os.environ['PORT'])),H).serve_forever()")

pytestmark = pytest.mark.docker


def _daemon():
    if not shutil.which("docker"):
        return False
    return subprocess.run(["docker", "version"], capture_output=True).returncode == 0


@pytest.mark.skipif(not _daemon(), reason="no docker daemon")
def test_a_container_is_placed_leased_and_stopped(home, tmp_path):
    d = Docker()
    ctx = tmp_path / "img"
    ctx.mkdir()
    (ctx / "shim.py").write_text(SHIM)
    (ctx / "Dockerfile").write_text("FROM python:3.12-slim\nCOPY shim.py /shim.py\nCMD [\"python\", \"/shim.py\"]\n")
    subprocess.run(["docker", "build", "-q", "-t", "bs-test-shim", str(ctx)], check=True, capture_output=True)
    registry.save({"shim": {"kind": "layout", "image": "bs-test-shim", "provider": "docker", "idle_s": 1}})
    f = Fleet({"docker": d}, boot_s=60)
    try:
        got = f.ensure("shim", "j1")
        assert got["endpoint"].startswith("http://127.0.0.1:") and got["lease"]
        p = f.placements()[0]
        assert p["state"] == "ready" and d.alive(p["handle"])
        assert any(h["id"] == p["handle"] and h["model"] == "shim" for h in d.list())
        f.release("j1")
        import time

        time.sleep(1.2)
        assert f.sweep() == [p["id"]]
        assert not d.alive(p["handle"]) and f.ledger()[-1]["why"] == "idle"
    finally:
        for p in f.placements():
            d.stop(p["handle"])
