import json
import subprocess

from fleet.errors import Refusal

LABEL = "bs.owner=fleet"


def _docker(*args: str, timeout: float = 120.0) -> str:
    p = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        raise Refusal(f"docker {args[0]}: {p.stderr.strip()[:300]}")
    return p.stdout.strip()


class Docker:
    name = "docker"

    def __init__(self, network: str = ""):
        self.network = network

    def available(self) -> bool:
        try:
            _docker("version", "--format", "{{.Server.Version}}", timeout=20)
            return True
        except (Refusal, OSError, subprocess.TimeoutExpired):
            return False

    def start(self, model: str, entry: dict, key: str) -> dict:
        port = entry["port"]
        cname = f"bs-svc-{model}-{key[:8]}"
        args = ["run", "-d", "--name", cname, "--label", LABEL, "--label", f"bs.model={model}",
                "-e", f"BOOKSMITH_SERVE_KEY={key}", "-e", f"BOOKSMITH_PORT={port}",
                "-e", f"BOOKSMITH_IDLE_S={int(entry['idle_s'] * 2 + 600)}"]
        for k, v in entry["env"].items():
            args += ["-e", f"{k}={v}"]
        if entry.get("gpu"):
            args += ["--gpus", "all"]
        if self.network:
            args += ["--network", self.network]
        else:
            args += ["-p", f"127.0.0.1:0:{port}"]
        cid = _docker(*args, entry["image"], timeout=600)[:12]
        if self.network:
            endpoint = f"http://{cname}:{port}"
        else:
            mapped = _docker("port", cid, f"{port}/tcp").split("\n")[0].rsplit(":", 1)[-1]
            endpoint = f"http://127.0.0.1:{mapped}"
        return {"id": cid, "endpoint": endpoint, "rate_usd_h": 0.0}

    def alive(self, handle: str) -> bool:
        try:
            return _docker("inspect", "-f", "{{.State.Running}}", handle, timeout=20) == "true"
        except Refusal:
            return False

    def stop(self, handle: str) -> None:
        try:
            _docker("rm", "-f", handle, timeout=60)
        except Refusal:
            pass

    def list(self) -> list[dict]:
        out = _docker("ps", "-a", "--filter", f"label={LABEL}", "--format", "{{json .}}", timeout=30)
        rows = [json.loads(line) for line in out.split("\n") if line.strip()]
        found = []
        for r in rows:
            labels = dict(kv.split("=", 1) for kv in r.get("Labels", "").split(",") if "=" in kv)
            found.append({"id": r["ID"][:12], "model": labels.get("bs.model", ""), "state": r.get("State", "")})
        return found


