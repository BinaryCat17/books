#!/usr/bin/env python3
"""Rent a GPU on vast.ai, run PaddleOCR-VL over a PDF, fetch the result, destroy.

    ./launch.py ../../bench/test25.pdf ../../bench/paddleocr
    ./launch.py ../../raw/book.pdf ../../processed/book_paddleocr --gpu RTX_5090

The instance is destroyed in a `finally:` block — on success, on error, and on
Ctrl-C.  `--keep` disables that for debugging; `--reap` destroys anything this
script left behind.

Needs:
    vastai set api-key <KEY>          (or VAST_API_KEY in tools/.env)
    vastai create ssh-key "$(cat ~/.ssh/id_ed25519.pub)"
"""
import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
VASTAI = os.path.join(HERE, "..", "venv", "bin", "vastai")

REGISTRY = "ccr-2vdh3abv-pub.cnc.bj.baidubce.com/paddlepaddle"
# Weights are baked into the *-offline images: nothing is downloaded at runtime.
#
# Use the *pipeline* image, not paddleocr-genai-vllm-server.  The server image
# ships only the VLM service -- it has no paddlex[ocr], so pipeline creation
# dies with a DependencyError.  Upstream runs the two as separate compose
# containers; a vast.ai instance is a single container, so we take the one that
# can do the whole job by itself.
#
# sm89 points at our GHCR mirror (see mirror_image.py): same image, but off a
# CDN edge instead of Beijing, where pulls ran at ~10 MB/s.  Pass --image to go
# back to the source.
MIRROR = "ghcr.io/binarycat17"
IMAGES = {
    "sm89": f"{MIRROR}/paddleocr-vl:offline",
    "sm120": f"{REGISTRY}/paddleocr-vl:latest-nvidia-gpu-sm120",
}
# Blackwell cards (sm_120) need the sm120 build; everything older uses the
# mainstream one.  Ada/Ampere are the well-trodden path.
BLACKWELL = ("RTX_5090", "RTX_5080", "RTX_5070", "B200", "RTX_PRO_6000")

SSH_OPTS = [
    "-o", "StrictHostKeyChecking=no",
    "-o", "UserKnownHostsFile=/dev/null",
    "-o", "LogLevel=ERROR",
    "-o", "ServerAliveInterval=20",
]


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def vast(*args, raw=True):
    """Run the vastai CLI and return parsed JSON (or text)."""
    cmd = [VASTAI] + list(args) + (["--raw"] if raw else [])
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"vastai {' '.join(args)} failed:\n{p.stderr.strip()}")
    if not raw:
        return p.stdout
    try:
        return json.loads(p.stdout)
    except json.JSONDecodeError:
        return p.stdout


def load_key():
    if os.environ.get("VAST_API_KEY"):
        return os.environ["VAST_API_KEY"]
    env = os.path.join(HERE, "..", ".env")
    if os.path.exists(env):
        for line in open(env):
            if line.startswith("VAST_API_KEY="):
                return line.split("=", 1)[1].strip()
    return None


# Measured, not guessed: a real docker pull got 103 Mbit on a host advertising
# 990 (10.4%), and 76 Mbit on one advertising 8301 (0.9%).  `inet_down` is a
# multi-stream speedtest of the whole machine; docker fetches 3 layers at a
# time over single HTTP streams, so one big layer = one TCP connection, which
# is bounded by latency rather than bandwidth.  Hence the pessimistic number --
# and hence a fast link buys much less than it looks like it should.
LINK_EFFICIENCY = 0.10
# Pulling is only half of a cold start: docker then unpacks ~6 GB into ~18 GB
# on disk, which is why hosts with slow storage stall after "Download complete".
UNPACK_RATIO = 3.0
WORK = "/root/ocrjob"   # the PaddleOCR images have no /workspace; make our own


def est_cost(offer, image_gb, minutes):
    """Total $ for one run: image pull + compute.

    Ranking on $/hr alone is wrong here — the docker image is tens of GB and
    comes from a registry in Beijing, so a cheap host on a thin link loses far
    more to the pull than it saves on the hourly rate.
    """
    down = max(float(offer.get("inet_down") or 1), 1)
    dl_s = image_gb * 8 * 1024 / (down * LINK_EFFICIENCY)
    # decompression is CPU+disk bound and runs after/alongside the download
    disk = max(float(offer.get("disk_bw") or 500), 100)
    unpack_s = image_gb * UNPACK_RATIO * 1024 / disk * 60
    setup_s = dl_s + unpack_s
    return offer["dph_total"] * (setup_s + minutes * 60) / 3600, setup_s


def pick_offer(gpu, max_dph, min_down, min_disk, image_gb, minutes, min_disk_bw=1500):
    q = (f"gpu_name={gpu} num_gpus=1 rentable=true verified=true "
         f"reliability>0.98 dph_total<{max_dph} inet_down>{min_down} "
         f"disk_space>{min_disk} disk_bw>{min_disk_bw} cuda_vers>=12.9")
    log(f"searching: {q}")
    offers = vast("search", "offers", q, "-o", "dph_total")
    if not offers:
        raise SystemExit(
            f"no offers for {gpu} under ${max_dph}/hr with >{min_down} Mbps.\n"
            "Loosen with --max-dph / --min-down, or try another --gpu.")

    scored = sorted(offers, key=lambda o: est_cost(o, image_gb, minutes)[0])
    log(f"ranked by est. total cost ({image_gb} GB image, {minutes} min compute):")
    for o in scored[:5]:
        cost, setup_s = est_cost(o, image_gb, minutes)
        log(f"  #{o['id']}  ${o['dph_total']:.3f}/hr  "
            f"{o.get('inet_down', 0):.0f} Mbps  {o.get('disk_bw', 0):.0f} MB/s disk  "
            f"setup~{setup_s/60:.1f}min  => ${cost:.3f}  machine {o.get('machine_id')}")
    return scored[0]


def wait_running(iid, timeout=2100):
    """Poll until the container is up.  This covers the docker image pull."""
    t0, last = time.time(), None
    while time.time() - t0 < timeout:
        rows = vast("show", "instance", str(iid))
        inst = rows[0] if isinstance(rows, list) else rows
        status = inst.get("actual_status")
        msg = (inst.get("status_msg") or "").strip().splitlines()
        note = msg[-1][:90] if msg else ""
        if (status, note) != last:
            log(f"  status={status} {note}")
            last = (status, note)
        # Don't also wait for ssh_host: some instances never publish it while
        # `vastai ssh-url` resolves fine, and waiting for it hangs silently
        # until the timeout with no log line to explain why.
        if status == "running":
            return inst
        if status in ("exited", "offline"):
            raise RuntimeError(f"instance {iid} died: {inst.get('status_msg')}")
        time.sleep(10)
    raise RuntimeError(f"instance {iid} not running after {timeout}s")


def ssh_target(iid):
    url = vast("ssh-url", str(iid), raw=False).strip()
    m = re.match(r"ssh://(\w+)@([\w\.\-]+):(\d+)", url)
    if not m:
        raise RuntimeError(f"cannot parse ssh-url: {url!r}")
    user, host, port = m.groups()
    return user, host, port


def wait_ssh(user, host, port, key, timeout=420):
    base = ["ssh", "-p", port] + SSH_OPTS + (["-i", key] if key else [])
    t0 = time.time()
    while time.time() - t0 < timeout:
        p = subprocess.run(base + [f"{user}@{host}", "true"],
                           capture_output=True, text=True, timeout=45)
        if p.returncode == 0:
            log(f"  ssh ready after {time.time()-t0:.0f}s")
            return base
        time.sleep(8)
    raise RuntimeError(f"ssh to {host}:{port} never came up:\n{p.stderr.strip()}")


def run(base, user, host, cmd, stream=True):
    full = base + [f"{user}@{host}", cmd]
    if not stream:
        p = subprocess.run(full, capture_output=True, text=True)
        return p.returncode, p.stdout + p.stderr
    p = subprocess.Popen(full, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True, bufsize=1)
    for line in p.stdout:
        print("    " + line.rstrip(), flush=True)
    return p.wait(), ""


def scp(key, port, src, dst, recursive=False):
    cmd = ["scp", "-P", port] + SSH_OPTS + (["-i", key] if key else [])
    if recursive:
        cmd.append("-r")
    cmd += [src, dst]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"scp failed: {p.stderr.strip()}")


def attach_key(iid, key_path):
    """Put our public key on the instance.

    Registering a key on the account is NOT enough: vast.ai only injects keys
    that are attached to the specific instance, and without this you get a
    'Permission denied (publickey)' after the image has already been pulled --
    an expensive way to find out.
    """
    pub = key_path + ".pub"
    if not os.path.exists(pub):
        log(f"  no public key at {pub}; relying on account defaults")
        return False
    pubkey = open(pub).read().strip()
    for attempt in range(5):
        try:
            vast("attach", "ssh", str(iid), pubkey)
            log("  ssh key attached to instance")
            return True
        except Exception as e:
            if attempt == 4:
                log(f"  could not attach ssh key: {e}")
            time.sleep(4)
    return False


def alive(iid):
    """True if the instance still exists (i.e. still costs money)."""
    try:
        rows = vast("show", "instances")
    except Exception:
        return True          # can't tell -> assume the worst, keep retrying
    return any(int(i.get("id", -1)) == int(iid) for i in rows)


def destroy(iid):
    """Destroy and *verify*.

    Two traps here, both learned the hard way: `destroy instance` prompts for
    confirmation (hence -y, else it silently aborts), and it exits 0 even when
    it aborted.  So the return code proves nothing — only re-querying does.
    """
    for attempt in range(5):
        try:
            vast("destroy", "instance", str(iid), "-y")
        except Exception as e:
            log(f"  destroy attempt {attempt+1} errored: {e}")
        time.sleep(4)
        if not alive(iid):
            log(f"instance {iid} DESTROYED and verified gone (billing stopped)")
            return True
        log(f"  still alive after attempt {attempt+1}, retrying")
    log(f"!!! COULD NOT DESTROY {iid} — IT IS STILL BILLING YOU.\n"
        f"!!! Kill it now: vastai destroy instance {iid} -y\n"
        f"!!! or https://cloud.vast.ai/instances/")
    return False


def reap():
    rows = vast("show", "instances")
    mine = [i for i in rows if (i.get("label") or "").startswith("ocr-")]
    if not mine:
        log("nothing to reap")
        return
    for i in mine:
        log(f"reaping {i['id']} ({i.get('label')})")
        destroy(i["id"])


def do_job(base, user, host, port, ssh_key, pdf, outdir):
    """Upload, parse, fetch.  Assumes the instance is up and reachable."""
    rc, out = run(base, user, host, f"mkdir -p {WORK} && echo ok", stream=False)
    if rc != 0:
        raise RuntimeError(f"cannot create {WORK} on instance: {out}")

    log("uploading job scripts + pdf...")
    dest = f"{user}@{host}:{WORK}/"
    scp(ssh_key, port, os.path.join(HERE, "remote_job.sh"), dest)
    scp(ssh_key, port, os.path.join(HERE, "remote_parse.py"), dest)
    scp(ssh_key, port, pdf, dest + "input.pdf")

    log("running PaddleOCR-VL ...")
    rc, _ = run(base, user, host,
                f"bash {WORK}/remote_job.sh {WORK}/input.pdf {WORK}/out")
    if rc != 0:
        raise RuntimeError(f"remote job exited {rc} — see log above")

    log("packing + downloading results...")
    run(base, user, host,
        f"cd {WORK} && tar czf out.tgz out vllm.log job.log 2>/dev/null || "
        f"tar czf out.tgz out", stream=False)
    scp(ssh_key, port, f"{user}@{host}:{WORK}/out.tgz",
        os.path.join(outdir, "out.tgz"))
    subprocess.run(["tar", "xzf", "out.tgz"], cwd=outdir, check=True)
    os.remove(os.path.join(outdir, "out.tgz"))


def run_job_on(iid, a, destroy_after):
    """Run on an instance that already exists -- no rent, no cold start."""
    if not a.pdf or not a.outdir:
        raise SystemExit("pdf and outdir are required with --reuse")
    pdf, outdir = os.path.abspath(a.pdf), os.path.abspath(a.outdir)
    if not os.path.exists(pdf):
        raise SystemExit(f"no such file: {pdf}")
    os.makedirs(outdir, exist_ok=True)
    ssh_key = a.ssh_key if os.path.exists(a.ssh_key) else None

    log(f"reusing instance {iid} (skipping the cold start entirely)")
    t0, ok = time.time(), False
    try:
        wait_running(iid, timeout=300)
        user, host, port = ssh_target(iid)
        base = wait_ssh(user, host, port, ssh_key)
        do_job(base, user, host, port, ssh_key, pdf, outdir)
        ok = True
    finally:
        if destroy_after:
            destroy(iid)
        else:
            log(f"instance {iid} left running for the next --reuse "
                f"(it IS still billing)")
        log(f"job took {(time.time()-t0)/60:.1f} min")
    if ok:
        log(f"results in {outdir}")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", nargs="?", help="local PDF to process")
    ap.add_argument("outdir", nargs="?", help="local directory for results")
    ap.add_argument("--gpu", default="RTX_4090",
                    help="vast gpu_name, e.g. RTX_4090 / RTX_5090 / RTX_3090")
    ap.add_argument("--max-dph", type=float, default=0.60, help="price ceiling $/hr")
    ap.add_argument("--min-down", type=int, default=300,
                    help="min Mbps down; the image pull dominates setup time")
    ap.add_argument("--disk", type=int, default=60, help="instance disk GB")
    ap.add_argument("--image-gb", type=float, default=25.0,
                    help="assumed image size, used to rank offers by total cost")
    ap.add_argument("--minutes", type=float, default=12.0,
                    help="expected compute minutes, used for the same ranking")
    ap.add_argument("--min-disk-bw", type=int, default=1500,
                    help="min disk MB/s; slow storage stalls the unpack phase")
    ap.add_argument("--machine", type=int,
                    help="pin to a machine_id that already cached the image")
    ap.add_argument("--image", help="override docker image")
    ap.add_argument("--ssh-key",
                    default=os.path.expanduser("~/.ssh/id_ed25519_vast"))
    ap.add_argument("--keep", action="store_true",
                    help="leave the instance running so the next job can --reuse it")
    ap.add_argument("--reuse", type=int, metavar="ID",
                    help="run on an already-running instance instead of renting "
                         "one; skips the whole cold start")
    ap.add_argument("--dry-run", action="store_true", help="only show offers")
    ap.add_argument("--reap", action="store_true", help="destroy leftover instances")
    a = ap.parse_args()

    key = load_key()
    if key:
        os.environ["VAST_API_KEY"] = key

    if a.reap:
        return reap()

    if a.reuse:
        return run_job_on(a.reuse, a, destroy_after=not a.keep)

    image = a.image or IMAGES["sm120" if a.gpu in BLACKWELL else "sm89"]
    log(f"gpu={a.gpu}  image={image}")
    if a.gpu in BLACKWELL:
        log("  note: the sm120 build is vendor-verified on RTX 5070 only")

    offer = pick_offer(a.gpu, a.max_dph, a.min_down, a.disk, a.image_gb,
                       a.minutes, a.min_disk_bw)
    if a.machine:
        offers = vast("search", "offers",
                      f"machine_id={a.machine} num_gpus=1 rentable=true", "-o", "dph_total")
        if not offers:
            raise SystemExit(f"machine {a.machine} has no rentable offer right now")
        offer = offers[0]
        log(f"pinned to machine {a.machine}: offer #{offer['id']}")

    if a.dry_run:
        log(f"dry run — would rent #{offer['id']} at ${offer['dph_total']:.3f}/hr")
        return 0
    if not a.pdf or not a.outdir:
        ap.error("pdf and outdir are required (unless --reap/--dry-run)")

    pdf = os.path.abspath(a.pdf)
    outdir = os.path.abspath(a.outdir)
    if not os.path.exists(pdf):
        raise SystemExit(f"no such file: {pdf}")
    os.makedirs(outdir, exist_ok=True)
    ssh_key = a.ssh_key if os.path.exists(a.ssh_key) else None
    if not ssh_key:
        log(f"warning: {a.ssh_key} not found, relying on ssh-agent default key")

    dph = offer["dph_total"]
    label = f"ocr-{os.path.basename(pdf)[:24]}"
    log(f"renting offer #{offer['id']} at ${dph:.3f}/hr, {a.disk} GB disk")
    res = vast("create", "instance", str(offer["id"]),
               "--image", image, "--disk", str(a.disk),
               "--ssh", "--direct", "--label", label,
               # .no_auto_tmux is essential: without it vast's sshd ForceCommand
               # drops every connection into tmux and swallows the command, so
               # `ssh host 'cmd'` prints "no sessions" and runs nothing.
               "--onstart-cmd",
               f"touch /root/.no_auto_tmux; mkdir -p {WORK}; sleep infinity")
    iid = res.get("new_contract")
    if not iid:
        raise SystemExit(f"create failed: {res}")
    log(f"instance {iid} created")
    if ssh_key:
        attach_key(iid, ssh_key)

    t0 = time.time()
    ok = False
    try:
        log("waiting for image pull + boot (this is the slow part)...")
        wait_running(iid)
        user, host, port = ssh_target(iid)
        log(f"ssh {user}@{host}:{port}")
        base = wait_ssh(user, host, port, ssh_key)
        setup = time.time() - t0
        log(f"ready in {setup/60:.1f} min  (~${dph*setup/3600:.3f} spent so far)")

        do_job(base, user, host, port, ssh_key, pdf, outdir)
        ok = True
    finally:
        elapsed = time.time() - t0
        if a.keep:
            log(f"--keep set: instance {iid} STILL RUNNING and billing. "
                f"Destroy with: vastai destroy instance {iid}")
        else:
            destroy(iid)
        log(f"total {elapsed/60:.1f} min  ≈ ${dph*elapsed/3600:.3f}")

    if ok:
        log(f"results in {outdir}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
