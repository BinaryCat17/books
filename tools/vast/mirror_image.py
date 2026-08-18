#!/usr/bin/env python3
"""Mirror the PaddleOCR images from Baidu's registry to GHCR, once.

Pulling from ccr-2vdh3abv-pub.cnc.bj.baidubce.com (Beijing) took 8-14 min per
run and threw retries.  Copied to GHCR, the same image comes off a CDN edge in
2-3 min from anywhere.  This pays for itself on the second run.

The copy is registry-to-registry via skopeo, so it needs no docker daemon and
never lands the 30 GB on your home connection -- it streams through a rented
instance with a 10 Gbit link.  Costs about $0.05.

Credentials come from tools/.env (never argv, never the onstart script, which
vast.ai stores and shows in its console):

    GHCR_USER=<your github login>
    GHCR_TOKEN=<PAT with write:packages>

Write them there yourself; this script only reads the file and pipes the token
to `skopeo login --password-stdin`.

    ./mirror_image.py                 # mirror the pipeline image
    ./mirror_image.py --also-server   # mirror the vLLM server image too
"""
import argparse
import os
import subprocess
import sys
import time

import launch as L   # reuse offer search / ssh / destroy-and-verify

SRC = "ccr-2vdh3abv-pub.cnc.bj.baidubce.com/paddlepaddle"
# debian:12 pulls in seconds from Docker Hub and takes vast's sshd injection
# without complaint -- unlike the paddleocr images, which broke key injection.
BASE = "debian:12"

TARGETS = [
    ("paddleocr-vl", "latest-nvidia-gpu-offline", "offline"),
]
SERVER_TARGET = ("paddleocr-genai-vllm-server", "latest-nvidia-gpu-offline", "offline")


def load_creds():
    env = os.path.join(L.HERE, "..", ".env")
    creds = {}
    if os.path.exists(env):
        for line in open(env):
            for k in ("GHCR_USER", "GHCR_TOKEN"):
                if line.startswith(k + "="):
                    creds[k] = line.split("=", 1)[1].strip()
    for k in ("GHCR_USER", "GHCR_TOKEN"):
        if os.environ.get(k):
            creds[k] = os.environ[k]
    missing = [k for k in ("GHCR_USER", "GHCR_TOKEN") if not creds.get(k)]
    if missing:
        sys.exit(
            f"missing {', '.join(missing)}.\n"
            f"Add them to {os.path.abspath(env)} in your own terminal:\n"
            "    umask 077\n"
            "    echo 'GHCR_USER=yourlogin'  >> tools/.env\n"
            "    echo 'GHCR_TOKEN=ghp_xxxx'  >> tools/.env\n"
            "GHCR token: github.com/settings/tokens -> classic -> write:packages")
    return creds


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gpu", default="RTX_3090", help="cheapest card; GPU is unused here")
    ap.add_argument("--max-dph", type=float, default=0.40)
    ap.add_argument("--min-down", type=int, default=2000, help="Mbps; this is the point")
    ap.add_argument("--disk", type=int, default=120)
    ap.add_argument("--also-server", action="store_true")
    ap.add_argument("--ssh-key", default=os.path.expanduser("~/.ssh/id_ed25519_vast"))
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    creds = load_creds()
    user_gh, token = creds["GHCR_USER"], creds["GHCR_TOKEN"]
    targets = list(TARGETS) + ([SERVER_TARGET] if a.also_server else [])

    # Ranking weight: this job is pure download, so treat it as ~0 compute.
    offer = L.pick_offer(a.gpu, a.max_dph, a.min_down, a.disk, 30.0, 0.0)
    dph = offer["dph_total"]
    ssh_key = a.ssh_key if os.path.exists(a.ssh_key) else None

    L.log(f"renting #{offer['id']} at ${dph:.3f}/hr for the copy")
    res = L.vast("create", "instance", str(offer["id"]),
                 "--image", BASE, "--disk", str(a.disk),
                 "--ssh", "--direct", "--label", "ocr-mirror",
                 "--onstart-cmd",
                 "touch /root/.no_auto_tmux; "
                 "apt-get update -qq && apt-get install -y -qq skopeo ca-certificates; "
                 "sleep infinity")
    iid = res.get("new_contract")
    if not iid:
        sys.exit(f"create failed: {res}")
    L.log(f"instance {iid} created")
    if ssh_key:
        L.attach_key(iid, ssh_key)

    t0, ok = time.time(), False
    try:
        L.wait_running(iid)
        u, host, port = L.ssh_target(iid)
        base = L.wait_ssh(u, host, port, ssh_key)
        L.log(f"ready in {(time.time()-t0)/60:.1f} min; waiting for skopeo to install")

        for _ in range(60):
            rc, _out = L.run(base, u, host, "command -v skopeo", stream=False)
            if rc == 0:
                break
            time.sleep(10)
        else:
            raise RuntimeError("skopeo never installed; check the instance")

        # Token goes over stdin, so it appears in no argv and no log.
        L.log("logging in to ghcr.io ...")
        p = subprocess.run(
            base + [f"{u}@{host}", f"skopeo login ghcr.io -u {shell_q(user_gh)} "
                                   f"--password-stdin"],
            input=token, capture_output=True, text=True)
        if p.returncode != 0:
            raise RuntimeError(f"ghcr login failed: {p.stderr.strip()[:300]}")
        L.log("  login ok")

        for repo, src_tag, dst_tag in targets:
            src = f"docker://{SRC}/{repo}:{src_tag}"
            dst = f"docker://ghcr.io/{user_gh.lower()}/{repo}:{dst_tag}"
            L.log(f"copying {repo}:{src_tag}  ->  {dst.replace('docker://','')}")
            t1 = time.time()
            rc, _ = L.run(base, u, host,
                          f"skopeo copy --all --retry-times 5 {src} {dst}")
            if rc != 0:
                raise RuntimeError(f"skopeo copy failed for {repo}")
            L.log(f"  done in {(time.time()-t1)/60:.1f} min")
        ok = True
    finally:
        if a.keep:
            L.log(f"--keep: instance {iid} still billing")
        else:
            L.destroy(iid)
        L.log(f"total {(time.time()-t0)/60:.1f} min ≈ ${dph*(time.time()-t0)/3600:.3f}")

    if ok:
        L.log("Mirror done.  Now make the package public once, in the browser:")
        L.log(f"  https://github.com/users/{user_gh}/packages "
              "-> package -> Package settings -> Change visibility -> Public")
        L.log("Then point launch.py at it with --image "
              f"ghcr.io/{user_gh.lower()}/paddleocr-vl:offline")
    return 0 if ok else 1


def shell_q(s):
    return "'" + s.replace("'", "'\\''") + "'"


if __name__ == "__main__":
    sys.exit(main())
