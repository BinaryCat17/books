import os
import re
import select
import shlex
import subprocess
import tempfile
import threading
import time
from fleet import job
from fleet.errors import Cancelled
from fleet.log import log

_SOCK_DIR = os.path.join(tempfile.gettempdir(), f".fleet-{os.getuid()}")
try:
    os.makedirs(_SOCK_DIR, mode=448, exist_ok=True)
except OSError:
    _SOCK_DIR = tempfile.gettempdir()
SSH_OPTS = [
    "-o",
    "ControlMaster=auto",
    "-o",
    f"ControlPath={_SOCK_DIR}/%r@%h:%p",
    "-o",
    "ControlPersist=180",
    "-o",
    "ConnectTimeout=15",
    "-o",
    "StrictHostKeyChecking=no",
    "-o",
    "UserKnownHostsFile=/dev/null",
    "-o",
    "LogLevel=ERROR",
    "-o",
    "ServerAliveInterval=20",
    "-o",
    "ServerAliveCountMax=3",
]


class Box:
    def __init__(self, user: str, host: str, port: str, key: str | None, workdir: str):
        self.user, self.host, self.port = (user, host, port)
        self.key, self.workdir = (key, workdir)
        self._stop_sync = threading.Event()
        self._sync_thread: threading.Thread | None = None
        self._stop_hb = threading.Event()
        self._hb_thread: threading.Thread | None = None
        self.deadman = "not checked"

    @property
    def _ssh(self) -> list[str]:
        return ["ssh", "-p", self.port] + SSH_OPTS + (["-i", self.key] if self.key else [])

    @property
    def _addr(self) -> str:
        return f"{self.user}@{self.host}"

    def _run(self, cmd: list, timeout: float | None = None) -> subprocess.CompletedProcess:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        t0 = time.time()
        while True:
            try:
                out, err = p.communicate(timeout=1.0)
                return subprocess.CompletedProcess(cmd, p.returncode, out, err)
            except subprocess.TimeoutExpired:
                stopped = job.current().stop.is_set()
                if stopped or (timeout is not None and time.time() - t0 > timeout):
                    p.kill()
                    p.communicate()
                    if stopped:
                        job.current().check()
                    raise subprocess.TimeoutExpired(cmd, timeout) from None

    def wait_ready(self, timeout: float = 420) -> None:
        t0, err = (time.time(), "")
        while time.time() - t0 < timeout:
            job.current().check()
            try:
                p = self._run(self._ssh + [self._addr, "true"], timeout=45)
            except subprocess.TimeoutExpired:
                err = "ssh did not answer in 45 s"
                continue
            if p.returncode == 0:
                log(f"  ssh ready in {time.time() - t0:.0f} s")
                return
            err = p.stderr.strip()
            time.sleep(8)
        raise RuntimeError(f"ssh on {self.host}:{self.port} never came up:\n{err}")

    def run(self, cmd: str, stream: bool = True, deadline: float | None = None) -> tuple[int, str]:
        full = self._ssh + [self._addr, cmd]
        if not stream:
            if deadline is not None and deadline <= time.time():
                return (124, f"deadline gone before the start: {cmd[:80]}")
            limit = None if deadline is None else deadline - time.time()
            try:
                p = self._run(full, timeout=limit)
            except subprocess.TimeoutExpired:
                return (124, f"ssh missed the deadline: {cmd[:80]}")
            return (p.returncode, p.stdout + p.stderr)
        p = subprocess.Popen(full, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        try:
            while True:
                if job.current().stop.is_set():
                    p.kill()
                    p.wait(timeout=10)
                    job.current().check()
                ready, _, _ = select.select([p.stdout], [], [], 5.0)
                if ready:
                    line = p.stdout.readline()
                    if not line:
                        break
                    log("    " + line.rstrip(), remote=True)
                elif p.poll() is not None:
                    break
                if deadline and time.time() > deadline:
                    log("!!! budget/timeout spent -- killing the job")
                    p.kill()
                    p.wait(timeout=10)
                    return (124, "")
        finally:
            if p.poll() is None:
                try:
                    p.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    p.kill()
        return (p.wait(), "")

    def probe(self, seconds: float = 12.0, mb_cap: int = 64) -> float:
        cmd = (
            self._ssh
            + ["-o", "ControlMaster=no"]
            + [self._addr, f"head -c {mb_cap * 1024 * 1024} /dev/urandom"]
        )
        t0 = time.time()
        got = 0
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        try:
            while time.time() - t0 < seconds:
                chunk = p.stdout.read(65536)
                if not chunk:
                    break
                got += len(chunk)
        finally:
            p.kill()
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        dt = max(time.time() - t0, 1e-06)
        return got * 8 / 1000000.0 / dt

    PROBE_FILE_BYTES = 20225497

    def probe_download(self, streams: int = 6, timeout: float = 40.0) -> float:
        url = "https://files.pythonhosted.org/packages/source/n/numpy/numpy-2.2.0.tar.gz"
        streams = max(1, int(streams))
        chunk = self.PROBE_FILE_BYTES // streams
        parts = " ".join(
            f"curl -sSL -o /dev/null --max-time {int(timeout)} -w '%{{size_download}}\n' -r {i * chunk}-{(self.PROBE_FILE_BYTES - 1 if i == streams - 1 else (i + 1) * chunk - 1)} {url} &"
            for i in range(streams)
        )
        cmd = f"S=$(date +%s%N); {{ {parts} wait; }} > /tmp/.dl; E=$(date +%s%N); echo GOT $(awk '{{s+=$1}} END {{print s+0}}' /tmp/.dl) NS $(( E - S ))"
        rc, out = self.run(cmd, stream=False, deadline=time.time() + timeout + 20)
        got = ns = 0
        for line in out.splitlines():
            if line.startswith("GOT "):
                try:
                    _, g, _, n = line.split()
                    got, ns = (int(g), int(n))
                except Exception:
                    return 0.0
        if ns <= 0:
            return 0.0
        want = self.PROBE_FILE_BYTES
        if got < want * 0.5:
            return 0.0
        return got * 8000.0 / ns

    RSYNC_TIMEOUT_S = 1800

    def _rsync(self, src: str, dst: str, extra: list[str] | None = None, timeout: float | None = None) -> int:
        rsh = " ".join(
            shlex.quote(x)
            for x in ["ssh", "-p", self.port] + SSH_OPTS + (["-i", self.key] if self.key else [])
        )
        cmd = ["rsync", "-az", "--partial", "-e", rsh] + (extra or []) + [src, dst]
        try:
            p = self._run(cmd, timeout=timeout or self.RSYNC_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            log(f"  rsync overran {(timeout or self.RSYNC_TIMEOUT_S) / 60:.0f} min -- cut off")
            return 124
        if p.returncode != 0:
            log(f"  rsync: {p.stderr.strip()[:200]}")
        return p.returncode

    _STAT_SIZE = re.compile("Total transferred file size:\\s*([\\d,]+)")
    _STAT_FILES = re.compile("Number of files:\\s*[\\d,]+\\s*\\(reg:\\s*([\\d,]+)")

    def _dry_stats(self, src: str, dst: str, exclude=()):
        extra = ["--dry-run", "--stats"] + [f"--exclude={x}" for x in exclude]
        rsh = " ".join(
            shlex.quote(x)
            for x in ["ssh", "-p", self.port] + SSH_OPTS + (["-i", self.key] if self.key else [])
        )
        cmd = ["rsync", "-az", "--partial", "-e", rsh] + extra + [src, dst]
        try:
            p = self._run(cmd, timeout=600)
        except subprocess.TimeoutExpired:
            return None
        if p.returncode != 0:
            return None
        m1 = self._STAT_SIZE.search(p.stdout)
        m2 = self._STAT_FILES.search(p.stdout)
        if not m1:
            return None
        return (int(m1.group(1).replace(",", "")), int(m2.group(1).replace(",", "")) if m2 else -1)

    def weigh_exclude(self, remote_rel: str, exclude: tuple, local_dir: str):
        src = f"{self._addr}:{self.workdir}/{remote_rel}/"
        dst = local_dir.rstrip("/") + "/"
        full = self._dry_stats(src, dst)
        if full is None:
            log("  could not weigh the exclusions -- rsync did not answer")
            return []
        rows = []
        for pat in exclude:
            got = self._dry_stats(src, dst, exclude=(pat,))
            if got is None:
                rows.append((pat, None, None))
                continue
            rows.append((pat, full[0] - got[0], max(full[1] - got[1], 0)))
        kept = self._dry_stats(src, dst, exclude=tuple(exclude)) if exclude else full
        log(f"  fetch of {remote_rel}: {full[0] / 1000000.0:.1f} MB total in {full[1]} files")
        for pat, b, f in rows:
            if b is None:
                log(f"  exclusion {pat}: could not measure")
            else:
                log(
                    f"  exclusion {pat}: {b / 1000000.0:.1f} MB, {f} files ({100.0 * b / max(full[0], 1):.1f}% of the fetch) -- WILL NOT ARRIVE"
                )
        if kept:
            log(f"  arriving: {kept[0] / 1000000.0:.1f} MB in {kept[1]} files")
        return rows

    def push(self, local: str, remote_rel: str) -> None:
        dst = f"{self._addr}:{self.workdir}/{remote_rel}"
        src = local
        if os.path.isdir(local):
            src = local.rstrip("/") + "/"
            dst = dst.rstrip("/") + "/"
        parent = os.path.dirname(remote_rel.rstrip("/"))
        if parent:
            self.run(
                "mkdir -p " + shlex.quote(f"{self.workdir}/{parent}"),
                stream=False,
                deadline=time.time() + self.SHORT_CMD_S,
            )
        rc = self._rsync(src, dst)
        if rc != 0:
            log("  rsync failed, falling back to scp")
            cmd = ["scp", "-P", self.port] + SSH_OPTS + (["-i", self.key] if self.key else [])
            scp_src = local
            if os.path.isdir(local):
                cmd.append("-r")
                scp_src = local.rstrip("/") + "/."
            cmd += [scp_src, f"{self._addr}:{self.workdir}/{remote_rel}"]
            p = self._run(cmd)
            if p.returncode != 0:
                raise RuntimeError(f"upload of {local} failed: {p.stderr.strip()}")

    def pull(
        self,
        remote_rel: str,
        local_dir: str,
        quiet: bool = False,
        exclude: tuple[str, ...] = (),
        timeout: float | None = None,
    ) -> int:
        os.makedirs(local_dir, exist_ok=True)
        src = f"{self._addr}:{self.workdir}/{remote_rel}/"
        extra = [f"--exclude={x}" for x in exclude]
        rc = self._rsync(src, local_dir.rstrip("/") + "/", extra or None, timeout=timeout)
        if rc != 0 and (not quiet):
            log(f"  could not fetch {remote_rel} (code {rc})")
        return rc

    def start_heartbeat(self, every: float = 30) -> None:

        def loop():
            while not self._stop_hb.wait(every):
                try:
                    self._run(self._ssh + [self._addr, "touch /root/.alive"], timeout=30)
                except Exception:
                    pass

        self._stop_hb.clear()
        self._hb_thread = job.spawn(loop)

    def stop_heartbeat(self) -> None:
        self._stop_hb.set()
        t = getattr(self, "_hb_thread", None)
        if t is not None and t.is_alive():
            t.join(timeout=2)

    SHORT_CMD_S = 60.0

    def check_deadman(self, tries: int = 3, pause: float = 4.0) -> str:
        from .vast import DEADMAN_STATE

        state = ""
        for i in range(max(1, tries)):
            rc, out = self.run(
                f"cat {DEADMAN_STATE} 2>/dev/null",
                stream=False,
                deadline=time.time() + self.SHORT_CMD_S,
            )
            state = (out or "").strip()
            if rc == 0 and state.startswith("ARMED"):
                log(f"  dead-man's watch armed: {state}")
                self.deadman = state
                return state
            if i + 1 < max(1, tries):
                time.sleep(pause)
        self.deadman = state or "no report"
        log(f"!!! DEAD-MAN'S WATCH NOT ARMED: {self.deadman}")
        log(
            f"!!! Machine {self.host}:{self.port} WILL NOT KILL ITSELF if our process dies. Only we destroy it now: finally, signals, budget watchdog -- all three in this process."
        )
        return self.deadman

    def set_deadman(self, seconds: int) -> None:
        rc, out = self.run(
            f"echo {int(seconds)} > /root/.alive.grace.tmp && mv /root/.alive.grace.tmp /root/.alive.grace",
            stream=False,
            deadline=time.time() + self.SHORT_CMD_S,
        )
        if rc != 0:
            raise RuntimeError(f"watch not reset (rc={rc}): {out.strip()[:200]}")

    def start_sync(
        self, remote_rel: str, local_dir: str, every: float = 20, exclude: tuple[str, ...] = ()
    ) -> None:

        def loop():
            try:
                while not self._stop_sync.wait(every):
                    self.pull(remote_rel, local_dir, quiet=True, exclude=exclude, timeout=300)
            except Cancelled:
                return

        self._stop_sync.clear()
        self._sync_thread = job.spawn(loop)
        log(f"  background sync {remote_rel} -> {local_dir} every {every:.0f} s")

    def stop_sync(self) -> None:
        self._stop_sync.set()
        if self._sync_thread:
            self._sync_thread.join(timeout=180)
            if self._sync_thread.is_alive():
                log("  background sync still running, waiting again")
                self._sync_thread.join(timeout=180)
            self._sync_thread = None
