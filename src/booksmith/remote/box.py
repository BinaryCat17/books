"""Transport to the rented machine: ssh for commands, rsync for files.

rsync and not scp with a tar at the end, for one reason: it is incremental.
The result used to be packed once the job had computed everything, and a crash
on page 400 of 539 lost all of it.  Here `outputs/` is pulled as the work goes.
"""
import os
import re
import select
import shlex
import subprocess
import tempfile
import threading
import time

# One connection for every call to the machine.  Measured: five files uploaded
# is five rsyncs, five handshakes of 4-5 seconds -- a 10 KB file costs as much
# as 4.4 MB, and a three-pass run comes to 21 handshakes.
#
# The socket lives in ITS OWN directory, not straight in /tmp.  With a file on
# that path owned by another user, ssh does NOT fall back to an ordinary
# connection -- it fails outright:
#
#     unix_listener: cannot bind to path /tmp/.booksmith-… Permission denied
#     rc=255
#
# In a shared /tmp that is the "somebody once ran it under sudo" case: every
# later run fails AFTER the machine is taken, on a billing card.  Mode 0700
# also closes the planted socket -- ssh checks neither owner nor mode of an
# existing one, the path is guessable, and a socket that accepts and stays
# silent hangs ssh with no timeout.  The path is capped at 108 bytes (checked
# with `bind()`); the worst real case, numeric address and port, is 47 (the old
# count said 42: the five-digit port was forgotten), twofold headroom.
_SOCK_DIR = os.path.join(tempfile.gettempdir(), f".booksmith-{os.getuid()}")
try:
    os.makedirs(_SOCK_DIR, mode=0o700, exist_ok=True)
except OSError:
    _SOCK_DIR = tempfile.gettempdir()

SSH_OPTS = [
    "-o", "ControlMaster=auto",
    "-o", f"ControlPath={_SOCK_DIR}/%r@%h:%p",
    "-o", "ControlPersist=180",
    # Without this, ssh to a machine gone silent hangs forever -- checked with
    # multiplexing and without.  Multiplexing does not create the hang, it
    # lengthens it by nearly a minute and a half.
    "-o", "ConnectTimeout=15",
    "-o", "StrictHostKeyChecking=no",
    "-o", "UserKnownHostsFile=/dev/null",
    "-o", "LogLevel=ERROR",
    "-o", "ServerAliveInterval=20",
    "-o", "ServerAliveCountMax=3",
]


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


class Box:
    """A live machine to run commands on and keep files."""

    def __init__(self, user: str, host: str, port: str,
                 key: str | None, workdir: str):
        self.user, self.host, self.port = user, host, port
        self.key, self.workdir = key, workdir
        self._stop_sync = threading.Event()
        self._sync_thread: threading.Thread | None = None
        self._stop_hb = threading.Event()
        self._hb_thread: threading.Thread | None = None
        # The deadman report before it is asked for is "not checked".  An
        # empty string here would be the zero of not-understanding: "not
        # asked" read as "not armed".
        self.deadman = "not checked"

    # ------------------------------------------------------------ primitives
    @property
    def _ssh(self) -> list[str]:
        return ["ssh", "-p", self.port] + SSH_OPTS + (
            ["-i", self.key] if self.key else [])

    @property
    def _addr(self) -> str:
        return f"{self.user}@{self.host}"

    def wait_ready(self, timeout: float = 420) -> None:
        t0, err = time.time(), ""
        while time.time() - t0 < timeout:
            try:
                p = subprocess.run(self._ssh + [self._addr, "true"],
                                   capture_output=True, text=True, timeout=45)
            except subprocess.TimeoutExpired:
                # While the container comes up the port often does not answer
                # and ssh hangs: normal, not a failure.  The first such attempt
                # used to kill the run -- after the image was pulled and paid
                # for.
                err = "ssh did not answer in 45 s"
                continue
            if p.returncode == 0:
                log(f"  ssh ready in {time.time()-t0:.0f} s")
                return
            err = p.stderr.strip()
            time.sleep(8)
        raise RuntimeError(
            f"ssh on {self.host}:{self.port} never came up:\n{err}")

    def run(self, cmd: str, stream: bool = True,
            deadline: float | None = None) -> tuple[int, str]:
        """Run a command.  With stream=True the output comes to us line by line.

        `deadline` is absolute time (time.time()) past which the command is
        killed: a job must not outlive the money allotted to it.
        """
        full = self._ssh + [self._addr, cmd]
        if not stream:
            # `deadline` holds here too.  This branch used to ignore it and run
            # without `timeout`, so `set_deadman`, `probe_download` and `rm -rf`
            # could hang on a silent machine as long as they liked -- with the
            # meter running and the docstring promising otherwise.
            if deadline is not None and deadline <= time.time():
                # The term ran out BEFORE the start: no one-second grace and
                # no orphan on the machine.  The old `max(1.0, ...)` launched
                # ssh, killed the local client on timeout and moved on while the
                # remote command kept working.
                return 124, f"deadline gone before the start: {cmd[:80]}"
            limit = None if deadline is None else deadline - time.time()
            try:
                p = subprocess.run(full, capture_output=True, text=True,
                                   timeout=limit)
            except subprocess.TimeoutExpired:
                # 124 -- the same code `_rsync` answers with on timeout.
                return 124, f"ssh missed the deadline: {cmd[:80]}"
            return p.returncode, p.stdout + p.stderr

        p = subprocess.Popen(full, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, bufsize=1)
        # `for line in p.stdout` will not do: it blocks until the next output,
        # and the job goes silent for minutes (vLLM loading the model).  The
        # deadline check in such a loop is unreachable exactly when it is needed
        # most.
        try:
            while True:
                ready, _, _ = select.select([p.stdout], [], [], 5.0)
                if ready:
                    line = p.stdout.readline()
                    if not line:
                        break                      # EOF: the process ended
                    print("    " + line.rstrip(), flush=True)
                elif p.poll() is not None:
                    break
                if deadline and time.time() > deadline:
                    log("!!! budget/timeout spent -- killing the job")
                    p.kill()
                    p.wait(timeout=10)
                    return 124, ""
        finally:
            if p.poll() is None:
                # Normal end: ssh has closed stdout but is not reaped yet.
                # Killing here turns a successful run into -9.
                try:
                    p.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    p.kill()
        return p.wait(), ""

    # ---------------------------------------------------------------- files
    def probe(self, seconds: float = 12.0, mb_cap: int = 64) -> float:
        """How many Mbit/s the channel to this machine really gives.

        A host advertises its own access to the internet, not the path to us: a
        machine promising 1188 Mbit/s took seven and a half minutes over a
        3.5 MB input file (62 kbit/s) while pulling from PyPI normally, and the
        job not starting was the first news of it -- fifteen minutes and money
        gone.

        WE MEASURE BY TIME, NOT BY SIZE.  The probe used to demand EXACTLY 4 MB
        within 25 s and return 0.0 short of that, and a zero in `runner` means
        "the machine is broken": "we failed to receive" written down as "it
        cannot send", indistinguishable BY CONSTRUCTION.  Cost on 3 September
        2026: three good machines binned in a row, $0.081 and 13 minutes out of
        60.  The arithmetic -- 4 MB is 32 Mbit, our channel 2.8 Mbit/s over HTTP,
        one ssh stream about 41% of that (1.16 Mbit/s: 4 MB did not arrive in
        27.5 s), and the threshold, derived from the HTTP figure
        (`0.5*ours` = 1.42), stood ABOVE what our line can push through ssh.

        Reading for the time given leaves no false zeros: zero means "not one
        byte came".  A broken machine at 62 kbit/s hands over about 93 KB in
        12 s, 0.06 Mbit/s, below any sane threshold.  Data from /dev/urandom --
        zeros would compress in ssh and give a pretty lie; `mb_cap` only keeps
        the stream finite, 64 MB in 12 s needing 43 Mbit/s.
        """
        # THE PROBE DOES NOT BECOME THE MULTIPLEX MASTER.  Under
        # `ControlMaster=auto` the first connection becomes master of the shared
        # socket and the rest ride it -- and this probe READS ITS TIME OUT AND
        # KILLS ssh, taking down everything that follows.  That was the 87.5 MB
        # upload of 3 September 2026: "write error: Broken pipe (32)" after two
        # minutes, a fall back to scp, the loss of `--partial` and of resuming
        # where it broke.  `ControlMaster=no` uses a master, never becomes one.
        cmd = (self._ssh + ["-o", "ControlMaster=no"]
               + [self._addr, f"head -c {mb_cap * 1024 * 1024} /dev/urandom"])
        t0 = time.time()
        got = 0
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL)
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
        dt = max(time.time() - t0, 1e-6)
        return got * 8 / 1e6 / dt

    # Probe file size: ranges past its end return 416 and zero bytes.  Checked
    # with HEAD on 03.09.2026: `content-length: 20225497` after 302 -> 200.
    PROBE_FILE_BYTES = 20_225_497

    def probe_download(self, streams: int = 6, timeout: float = 40.0) -> float:
        """How many Mbit/s the machine pulls from the world, IN SEVERAL STREAMS.

        Several on purpose: uv fetches wheels over dozens of connections.  The
        first probe measured one stream over 8 MB -- almost pure TCP ramp-up --
        and gave an inverse relation: 154 Mbit/s where the wheels took 104 s,
        307 where the same wheels took 277 s.

        CHUNK LENGTH IS DERIVED FROM THE FILE, not passed in.  At `mb=12`,
        `streams=6` six ranges of 12 MiB cover 75.5 MB of a 20.2 MB file: the
        first stream pulled 12.6 MB, the second the remaining 7.6 MB, the last
        four asked past the end and got 416 and zero bytes.  The "six-stream
        probe" measured TWO.  Now `streams` chunks divide the file exactly.

        The number still only goes into the ledger: `MIN_DOWNLOAD_MBPS` stands
        at 0.0 and rejects nothing.  A threshold waits for enough pairs of
        "probe against wheel time" -- setting one off two points is the mistake
        already made.
        """
        url = ("https://files.pythonhosted.org/packages/source/n/numpy/"
               "numpy-2.2.0.tar.gz")
        streams = max(1, int(streams))
        chunk = self.PROBE_FILE_BYTES // streams
        # -L is mandatory: pythonhosted answers 302 here, and without it curl
        # downloads zero bytes in silence and the machine looks broken.  We
        # count the bytes that ARRIVED, not the ones ordered: the old edition
        # divided by the constant `chunk * streams`, while ranges past the end
        # return 416, which curl does not call an error.  A machine with no way
        # out answered instantly without a byte, the formula produced
        # ~3000 Mbit/s, that record went into the ledger and `fast_machines` put
        # the machine first.  The neighbouring `probe()` counts right; here
        # there was no check at all.
        #
        # The last chunk takes the remainder: at six streams 3 370 916 B per
        # stream and +1 B of tail, the file covered exactly once.
        parts = " ".join(
            f"curl -sSL -o /dev/null --max-time {int(timeout)} "
            f"-w '%{{size_download}}\n' "
            f"-r {i * chunk}-"
            f"{(self.PROBE_FILE_BYTES - 1) if i == streams - 1 else (i + 1) * chunk - 1}"
            f" {url} &"
            for i in range(streams))
        cmd = (f"S=$(date +%s%N); {{ {parts} wait; }} > /tmp/.dl; "
               f"E=$(date +%s%N); "
               f"echo GOT $(awk '{{s+=$1}} END {{print s+0}}' /tmp/.dl) "
               f"NS $(( E - S ))")
        rc, out = self.run(cmd, stream=False,
                           deadline=time.time() + timeout + 20)
        got = ns = 0
        for line in out.splitlines():
            if line.startswith("GOT "):
                try:
                    _, g, _, n = line.split()
                    got, ns = int(g), int(n)
                except Exception:
                    return 0.0
        if ns <= 0:
            return 0.0
        want = self.PROBE_FILE_BYTES
        if got < want * 0.5:
            # Less than half of what was ordered arrived, nothing to measure.
            # Zero here is an EXPLICIT "the probe did not work", not a fast
            # channel: the zero from a check and the zero from not understanding
            # are different zeros.
            return 0.0
        return got * 8000.0 / ns

# Ceiling on a single transfer.  Half an hour covers the worst seen with room
# to spare: 180 MB of images on a 2.9 Mbit/s link is about sixteen minutes.
# With no ceiling a stuck rsync hung forever -- the background sync thread never
# exited, `stop_sync` burned its three hundred seconds for nothing, and the
# final fetch never ended.
    RSYNC_TIMEOUT_S = 1800

    def _rsync(self, src: str, dst: str, extra: list[str] | None = None,
               timeout: float | None = None) -> int:
        rsh = " ".join(shlex.quote(x) for x in
                       ["ssh", "-p", self.port] + SSH_OPTS +
                       (["-i", self.key] if self.key else []))
        cmd = ["rsync", "-az", "--partial", "-e", rsh] + (extra or []) + [src, dst]
        try:
            p = subprocess.run(cmd, capture_output=True, text=True,
                               timeout=timeout or self.RSYNC_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            # `--partial` leaves the unfinished part in place, so the next
            # attempt continues instead of starting over.
            log(f"  rsync overran "
                f"{(timeout or self.RSYNC_TIMEOUT_S)/60:.0f} min -- cut off")
            return 124
        if p.returncode != 0:
            log(f"  rsync: {p.stderr.strip()[:200]}")
        return p.returncode

    _STAT_SIZE = re.compile(r"Total transferred file size:\s*([\d,]+)")
    _STAT_FILES = re.compile(r"Number of files:\s*[\d,]+\s*\(reg:\s*([\d,]+)")

    def _dry_stats(self, src: str, dst: str, exclude=()):
        """How many bytes and files would go.  rsync counts it itself, dry."""
        extra = ["--dry-run", "--stats"] + [f"--exclude={x}" for x in exclude]
        rsh = " ".join(shlex.quote(x) for x in
                       ["ssh", "-p", self.port] + SSH_OPTS +
                       (["-i", self.key] if self.key else []))
        cmd = ["rsync", "-az", "--partial", "-e", rsh] + extra + [src, dst]
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        except subprocess.TimeoutExpired:
            return None
        if p.returncode != 0:
            return None
        m1 = self._STAT_SIZE.search(p.stdout)
        m2 = self._STAT_FILES.search(p.stdout)
        if not m1:
            return None
        return (int(m1.group(1).replace(",", "")),
                int(m2.group(1).replace(",", "")) if m2 else -1)

    def weigh_exclude(self, remote_rel: str, exclude: tuple, local_dir: str):
        """The weight of each exclusion in bytes -- measured, not guessed.

        Measured BY rsync and dry: `--dry-run --stats` without the exclusions
        and with them, the difference is the weight.  Not `du`, not `find`:
        rsync reads a pattern its own way -- `pages/*.json` is not
        `pages/**.json` to it, `imgs/` is not `imgs` -- and measuring by one
        reading while uploading by another gives a ledger number with no bearing
        on what did not arrive.  Dry costs one directory walk and zero bytes.

        Why it exists.  Per-page json was excluded along with the images, which
        looked like thrift until someone named the price: 6.55 MB out of 822 on
        the wire, 0.8% of the upload, because rsync squeezes json 6.9 times and
        images 1.04.  For those 0.8% four books of six lost their per-page
        layout -- the only record of where the block frames stood.  An exclusion
        whose price was never named is cheap only in appearance.

        Returns `(pattern, bytes, files)` rows; the totals go to the log.
        """
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
        log(f"  fetch of {remote_rel}: {full[0]/1e6:.1f} MB total "
            f"in {full[1]} files")
        for pat, b, f in rows:
            if b is None:
                log(f"  exclusion {pat}: could not measure")
            else:
                log(f"  exclusion {pat}: {b/1e6:.1f} MB, {f} files "
                    f"({100.0*b/max(full[0],1):.1f}% of the fetch) "
                    f"-- WILL NOT ARRIVE")
        if kept:
            log(f"  arriving: {kept[0]/1e6:.1f} MB in {kept[1]} files")
        return rows

    def push(self, local: str, remote_rel: str) -> None:
        """Put a file or a DIRECTORY exactly where it is named.

        `rsync SRC DST` is not `cp -r`: a source WITHOUT a trailing slash always
        lands INSIDE the destination, existing or not.  Measured with local
        rsync 3.2.7 on a `pkg` directory of two files:

            rsync -az --partial src/pkg  d1/pkg   -> d1/pkg/pkg/f.txt
            rsync -az --partial src/pkg  d2/pkg   -> d2/pkg/pkg/f.txt (d2/pkg existed)
            rsync -az --partial src/pkg/ d3/pkg/  -> d3/pkg/f.txt      AS WANTED

        The cost is the whole rental: the second-level job carries TWO
        directories to the box (`src/booksmith` -> `booksmith`, the layout ->
        `detect`), and they would land as `/root/job/booksmith/booksmith/…` --
        `import booksmith` finding a directory without `__init__.py`,
        `detect/pages` finding no pages, both loud but only after nine gigabytes
        of wheels and vLLM coming up.  The previous job (`dots_ocr`) carried
        files only, where the slash does not matter.

        scp has a THIRD semantics, so the fallback needs its own fix.  Same
        OpenSSH 9.6:

            scp -r src/pkg  s1/pkg  -> s1/pkg/f.txt      (no destination)
            scp -r src/pkg  s2/pkg  -> s2/pkg/pkg/f.txt  (destination existed)
            scp -r src/pkg/ s3/pkg  -> s3/pkg/pkg/f.txt  the slash does NOT help
            scp -r src/pkg/. s4/pkg -> s4/pkg/f.txt      right in BOTH cases
        """
        dst = f"{self._addr}:{self.workdir}/{remote_rel}"
        src = local
        if os.path.isdir(local):
            src = local.rstrip("/") + "/"
            dst = dst.rstrip("/") + "/"
        # rsync creates only the LAST link of the path: `a/b` with `a` missing
        # fails on the rented machine.  The job directory is made earlier in
        # `execute`, so the extra call is only for nested names.
        parent = os.path.dirname(remote_rel.rstrip("/"))
        if parent:
            self.run("mkdir -p " + shlex.quote(f"{self.workdir}/{parent}"),
                     stream=False, deadline=time.time() + self.SHORT_CMD_S)
        rc = self._rsync(src, dst)
        if rc != 0:
            # rsync may be missing from the image despite onstart
            log("  rsync failed, falling back to scp")
            cmd = ["scp", "-P", self.port] + SSH_OPTS + (
                ["-i", self.key] if self.key else [])
            scp_src = local
            if os.path.isdir(local):
                cmd.append("-r")
                # `/.` instead of the bare directory: see the docstring --
                # only this form puts the contents in place whether the
                # destination exists or not.
                scp_src = local.rstrip("/") + "/."
            cmd += [scp_src, f"{self._addr}:{self.workdir}/{remote_rel}"]
            p = subprocess.run(cmd, capture_output=True, text=True)
            if p.returncode != 0:
                raise RuntimeError(
                    f"upload of {local} failed: {p.stderr.strip()}")

    def pull(self, remote_rel: str, local_dir: str, quiet: bool = False,
             exclude: tuple[str, ...] = (), timeout: float | None = None) -> int:
        """Fetch the result.  `exclude` is what not to pull at all.

        Needed when the result directory is mostly what we do not want.
        Measured on an earlier run: 179 MB in the directory, 167 of them images;
        on that run's link (2.9 Mbit/s), sixteen minutes of transfer for nothing.
        """
        os.makedirs(local_dir, exist_ok=True)
        src = f"{self._addr}:{self.workdir}/{remote_rel}/"
        extra = [f"--exclude={x}" for x in exclude]
        rc = self._rsync(src, local_dir.rstrip("/") + "/", extra or None,
                         timeout=timeout)
        if rc != 0 and not quiet:
            log(f"  could not fetch {remote_rel} (code {rc})")
        return rc

    # ------------------------------------------------------------ heartbeat
    def start_heartbeat(self, every: float = 30) -> None:
        """Show the machine that the operator is alive.

        The ONSTART deadman watches this file on the far side: not refreshed
        within its term, and the instance destroys itself.  Without a pulse the
        only switch was ours, and a local process dying left the machine billing
        into nowhere.

        Touch errors are swallowed on purpose: one missed attempt decides
        nothing (the term is minutes), and dropping a run that computes fine
        over it would be stupid.
        """
        def loop():
            while not self._stop_hb.wait(every):
                try:
                    subprocess.run(self._ssh + [self._addr, "touch /root/.alive"],
                                   capture_output=True, timeout=30)
                except Exception:
                    pass
        self._stop_hb.clear()
        self._hb_thread = threading.Thread(target=loop, daemon=True)
        self._hb_thread.start()

    def stop_heartbeat(self) -> None:
        """Stop the pulse -- mandatory before abandoning the machine.

        Without it the deadman is off exactly where it is needed most: a machine
        rejected on channel that could not be destroyed kept getting a pulse
        from our own thread and never killed itself.  And five rental attempts
        accumulated five threads, four knocking on dead hosts.
        """
        self._stop_hb.set()
        t = getattr(self, "_hb_thread", None)
        if t is not None and t.is_alive():
            t.join(timeout=2)

# Ceiling on a short service command.  A minute is ample for `echo`+`mv` over
# an open multiplexed connection, and without a ceiling `set_deadman`, called
# from `finally` AFTER `_ignore_signals()`, froze the run dead on a silent
# machine: Ctrl-C no longer took it and the ledger stayed unfinished.
    SHORT_CMD_S = 60.0

    def check_deadman(self, tries: int = 3, pause: float = 4.0) -> str:
        """Is the deadman armed ON THE MACHINE ITSELF.  Silence is not allowed.

        It is the only one of the four kill paths depending neither on our
        process nor on our key.  With an empty `CONTAINER_API_KEY` it stayed a
        live loop knocking `curl -X DELETE` with an empty Bearer twice a minute:
        indistinguishable from working, in fact off, and the bill for a
        forgotten machine would have been the first news of it.  ONSTART now
        writes a report to a file; this reads it.

        Three tries with a pause: a background onstart loop writes that report,
        ssh is usually ready after it, but the order cannot be relied on and a
        false alarm teaches one not to look at alarms at all.

        Returns the report line; it also goes into the run ledger.
        """
        # The path is declared next to the ONSTART that writes the file: there
        # must not be two copies of it.  Imported inside the method so `box.py`
        # does not pull the `vastai` package for one line.
        from .vast import DEADMAN_STATE
        state = ""
        for i in range(max(1, tries)):
            rc, out = self.run(f"cat {DEADMAN_STATE} 2>/dev/null", stream=False,
                               deadline=time.time() + self.SHORT_CMD_S)
            state = (out or "").strip()
            # `ARMED` in latin -- see ONSTART: the report goes through the vast
            # API, the machine's shell and ssh, and UTF-8 integrity on that path
            # cannot be checked without renting.
            if rc == 0 and state.startswith("ARMED"):
                log(f"  dead-man's watch armed: {state}")
                self.deadman = state
                return state
            if i + 1 < max(1, tries):
                time.sleep(pause)
        self.deadman = state or "no report"
        log(f"!!! DEAD-MAN'S WATCH NOT ARMED: {self.deadman}")
        log(f"!!! Machine {self.host}:{self.port} WILL NOT KILL ITSELF if "
            f"our process dies. Only we destroy it now: finally, signals, "
            f"budget watchdog -- all three in this process.")
        return self.deadman

    def set_deadman(self, seconds: int) -> None:
        """Reset the deadman term -- before --keep, for instance.

        Write to a temp file and move: `echo > file` on a broken ssh leaves the
        file EMPTY, and an empty value expands to `[ N -gt ]` -- a syntax error,
        that is a lie, that is a machine that never kills itself.  `mv` within
        one filesystem is atomic.

        The return code is examined, not swallowed: the caller used to print
        "deadman reset" whether ssh answered or returned 255.
        """
        rc, out = self.run(
            f"echo {int(seconds)} > /root/.alive.grace.tmp && "
            f"mv /root/.alive.grace.tmp /root/.alive.grace", stream=False,
            deadline=time.time() + self.SHORT_CMD_S)
        if rc != 0:
            raise RuntimeError(
                f"watch not reset (rc={rc}): {out.strip()[:200]}")

    # ------------------------------------------------------ background sync
    def start_sync(self, remote_rel: str, local_dir: str, every: float = 20,
                   exclude: tuple[str, ...] = ()) -> None:
        """Pull results as the work goes, not only at the end."""
        def loop():
            while not self._stop_sync.wait(every):
                # The background fetch gets a shorter ceiling: it repeats in
                # twenty seconds anyway and has no business hanging half an hour.
                self.pull(remote_rel, local_dir, quiet=True, exclude=exclude,
                          timeout=300)
        self._stop_sync.clear()
        self._sync_thread = threading.Thread(target=loop, daemon=True)
        self._sync_thread.start()
        log(f"  background sync {remote_rel} -> {local_dir} "
            f"every {every:.0f} s")

    def stop_sync(self) -> None:
        """Wait out the background fetch before starting the final one.

        Otherwise two rsyncs write into one directory at once, and the handle on
        the thread is lost.
        """
        self._stop_sync.set()
        if self._sync_thread:
            self._sync_thread.join(timeout=180)
            if self._sync_thread.is_alive():
                log("  background sync still running, waiting again")
                self._sync_thread.join(timeout=180)
            self._sync_thread = None
