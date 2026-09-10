"""Renting on vast.ai over the SDK.

The SDK and not the CLI, whose `destroy instance` asks for confirmation and
returns 0 even when it refuses to work -- a destruction reported while the money
runs on. The re-query check stays all the same: it costs one call.
"""
import os
import re
import time

from vastai import VastAI

from . import pricing
from .spec import HostReq, JobSpec
from booksmith.core.log import log
from booksmith.core import job
from booksmith.core.errors import Refusal

# ssh on a vast instance hijacks the login into tmux, so `ssh host 'cmd'` runs
# nothing; cured by this file, which also puts rsync in at once, or fetching
# results would not be incremental. authorized_keys permissions are fixed in a
# loop, not once: vast writes the file world-readable at an undefined moment, and
# sshd reads it on every connection.
#
# ------------------------------------------------------------ deadman watch
# The last switch lives on the rented machine: a loop destroys the instance with
# the container's own CONTAINER_API_KEY once /root/.alive, touched every 30
# seconds by the operator (Box.start_heartbeat), goes stale. The grace sits in a
# file and not in the loop: with --keep the instance is left without an operator
# on purpose and gets another number.
DEADMAN_GRACE_S = 900

# Where the watch reports it is armed; without the file nothing could check it,
# and an empty CONTAINER_API_KEY would look like work. The report holds
# quantities only -- pid, instance id, the length of the key and not the key.
DEADMAN_STATE = "/root/.deadman.state"

ONSTART = (
    "touch /root/.no_auto_tmux; "
    "mkdir -p {workdir}; "
    "touch /root/.alive; echo {grace} > /root/.alive.grace; "
    "(K=$CONTAINER_API_KEY; I=$CONTAINER_ID; "
    " E=/proc/1/environ; "
    " if [ -z \"$K\" ]; then "
    "   K=$(tr '\\0' '\\n' < $E | sed -n 's/^CONTAINER_API_KEY=//p' | head -1); fi; "
    " if [ -z \"$I\" ]; then "
    "   I=$(tr '\\0' '\\n' < $E | sed -n 's/^CONTAINER_ID=//p' | head -1); fi; "
    # The report is written from inside the background loop, right before
    # `while`: it testifies that the watch reached its loop with a key and an id,
    # not merely that onstart had them.
    # Latin words, and not for style: the string crosses the vast API, an onstart
    # file, the machine's shell and ssh, and UTF-8 over that path cannot be
    # checked without renting.
    " if [ -z \"$K\" ] || [ -z \"$I\" ]; then "
    "   echo \"NOT-ARMED key=${{#K}} id='$I'\" > {state}; exit 1; fi; "
    " echo \"ARMED pid=$$ id=$I key=${{#K}} grace={grace}s\" > {state}; "
    " while sleep 30; do "
    # A `case` and not `|| echo`: an empty file (a torn write) would give an
    # empty G and `[ N -gt ]`, a syntax error, and a machine that never kills
    # itself, its errors going into /root/deadman.log, which we do not fetch.
    "   G=$(cat /root/.alive.grace 2>/dev/null); "
    "   case \"$G\" in \'\'|0|*[!0-9]*) G={grace};; esac; "
    "   A=$(stat -c %Y /root/.alive 2>/dev/null || echo 0); "
    "   if [ $(( $(date +%s) - A )) -gt $G ]; then "
    "     curl -s -X DELETE -H \"Authorization: Bearer $K\" "
    "          https://console.vast.ai/api/v0/instances/$I/ ; "
    "   fi; "
    " done) >/root/deadman.log 2>&1 & "
    "(for i in $(seq 1 90); do "
    "   chmod 700 /root/.ssh 2>/dev/null; "
    "   chmod 600 /root/.ssh/authorized_keys 2>/dev/null; "
    "   sleep 2; "
    " done) >/dev/null 2>&1 & "
    "(command -v rsync >/dev/null || "
    " (apt-get update -qq && apt-get install -y -qq rsync)) >/tmp/onstart.log 2>&1; "
    "sleep infinity"
)




class Vast:
    def __init__(self, api_key: str | None = None):
        self.v = VastAI(api_key) if api_key else VastAI()

    # --------------------------------------------------------------- choice
    def offers(self, host: HostReq, image_gb: float, minutes: float,
               payload_gb: float = 0.0, warmup_s: float = 0.0) -> list[dict]:
        q = host.query()
        log(f"search: {q}, disk {host.disk_gb} GB")
        # `storage` is the disk the server prices `dph_total` against, SDK
        # default 5 GiB against the 60 we rent, and three things hang on that
        # price: the server-side `dph_total<max_dph` filter, our budget ceiling
        # and the ledger cost. At 60 GiB the hour is a median 3.8% dearer.
        found = self.v.search_offers(q, order="dph_total",
                                     storage=float(host.disk_gb))
        if not found:
            raise Refusal(
                f"no offers for {host.gpu} under ${host.max_dph}/hour.\n"
                "Loosen --max-dph / --min-down or take another card.")
        return pricing.rank(found, image_gb, minutes, payload_gb, warmup_s)

    def pick(self, host: HostReq, image_gb: float, minutes: float,
             prefer_machines: list[int] | None = None, show: int = 5,
             payload_gb: float = 0.0, warmup_s: float = 0.0,
             avoid: list[int] | None = None) -> dict:
        ranked = self.offers(host, image_gb, minutes, payload_gb, warmup_s)
        if avoid:
            ranked = [o for o in ranked if o.get("machine_id") not in avoid]
            if not ranked:
                raise Refusal("no usable offers left: every machine "
                                 "checked was rejected on channel")
        if prefer_machines:
            # A priority list, not a set: first comes whoever computed fastest
            # for us, and cheap and fast are different machines.
            by_machine = {}
            for o in ranked:
                by_machine.setdefault(o.get("machine_id"), o)
            for pos, mid in enumerate(prefer_machines, 1):
                if mid in by_machine:
                    log(f"machine {mid}: place {pos} in the preference "
                        f"list (by the ledger) -- taking it")
                    return by_machine[mid]
        log("offers by the full cost of a run:")
        for o in ranked[:show]:
            log("  " + pricing.describe(o))
        return ranked[0]

    # -------------------------------------------------------------- renting
    def create(self, offer_id: int, spec: JobSpec,
               on_created=None) -> int:
        """Create the instance and hand its id out at once.

        Binding the ssh key does not belong in here: through its retries the
        instance exists and takes money while the caller does not know its id,
        so a Ctrl-C in that window would have nothing to destroy.
        """
        res = self.v.create_instance(
            id=int(offer_id),
            image=spec.image,
            disk=spec.host.disk_gb,
            label=spec.label(),
            env=spec.env or {},
            runtype="ssh_direc ssh_proxy",
            onstart_cmd=ONSTART.format(workdir=spec.workdir,
                                       grace=DEADMAN_GRACE_S,
                                       state=DEADMAN_STATE),
            # Without this a failed placement silently creates a stopped
            # instance that goes on charging for disk.
            cancel_unavail=True,
        )
        iid = res.get("new_contract")
        if not iid:
            raise Refusal(f"could not create the instance: {res}")
        log(f"instance {iid} created")
        if on_created:
            on_created(int(iid))       # before all else: it is already billing
        return int(iid)

    def attach_key(self, iid: int, key_path: str) -> bool:
        """A key registered on the account does not reach the instance.

        It must be attached to this very instance, or you get `Permission
        denied (publickey)` -- after the image has been downloaded.
        """
        pub = key_path + ".pub"
        if not os.path.exists(pub):
            log(f"  no public key at {pub}; hoping for the account keys")
            return False
        pubkey = open(pub).read().strip()
        for attempt in range(5):
            try:
                self.v.attach_ssh(instance_id=int(iid), ssh_key=pubkey)
                log("  ssh key attached to the instance")
                return True
            except Exception as e:
                if attempt == 4:
                    log(f"  could not attach the key: {e}")
                time.sleep(4)
        return False

    # --------------------------------------------------------------- status
    def instance(self, iid: int) -> dict | None:
        """The instance description; None only when it surely does not exist.

        On a request error we raise rather than return None: the caller must tell
        "they answered that the machine is gone" from "we could not ask".
        Polarity as in alive(): unknown is not dead.
        """
        rows = self.v.show_instance(id=int(iid))
        return rows[0] if isinstance(rows, list) and rows else (
            rows if isinstance(rows, dict) else None)

    def wait_running(self, iid: int, timeout: float = 2100) -> dict:
        """Wait for the container to start. The image download happens in here.

        Waiting for the `ssh_host` field as well is not allowed: some instances
        never publish it while `ssh_url` answers fine, and the loop then hangs
        to the timeout explaining nothing in the log.
        """
        t0, last = time.time(), None
        while time.time() - t0 < timeout:
            job.current().check()
            inst = self.instance(iid) or {}
            status = inst.get("actual_status")
            msg = (inst.get("status_msg") or "").strip().splitlines()
            note = msg[-1][:90] if msg else ""
            if (status, note) != last:
                log(f"  status={status} {note}")
                last = (status, note)
            if status == "running":
                return inst
            if status in ("exited", "offline"):
                raise RuntimeError(
                    f"instance {iid} died: {inst.get('status_msg')}")
            time.sleep(10)
        raise RuntimeError(f"instance {iid} did not come up in {timeout:.0f}s")

    def ssh_target(self, iid: int) -> tuple[str, str, str]:
        """The machine's address: direct first, the proxy as fallback.

        `ssh_url` hands out the sshN.vast.ai proxy, whose tunnel to the container
        sometimes does not come up at all while the direct port answers. Direct
        is also faster: rsync of the result crosses no relay.
        """
        inst = self.instance(iid) or {}
        ip = inst.get("public_ipaddr")
        mapped = (inst.get("ports") or {}).get("22/tcp") or []
        port = mapped[0].get("HostPort") if mapped else None
        if ip and port:
            return "root", str(ip).strip(), str(port)

        url = str(self.v.ssh_url(id=int(iid))).strip()
        m = re.match(r"ssh://(\w+)@([\w\.\-]+):(\d+)", url)
        if not m:
            raise RuntimeError(f"ssh-url does not parse: {url!r}")
        log("  no direct address -- going through the vast proxy")
        return m.groups()  # user, host, port

    # ---------------------------------------------------------- destruction
    def alive(self, iid: int) -> bool:
        """Does the instance exist, that is, is money still running."""
        try:
            rows = self.v.show_instances()
        except Exception:
            return True          # could not ask -> assume it is alive
        return any(str(i.get("id")) == str(iid) for i in rows)

    # The backoff grows: a flat pause answers a rate limit by hammering at the
    # same rate, and after such a burst the key returned 403 to everything. The
    # sum is two minutes, deliberately under the deadman grace, so even an
    # outright failure to destroy ends with the machine putting itself out.
    RETRY_S = (4, 8, 16, 32, 60)

    def destroy(self, iid) -> bool:
        """Kill an instance. Returns False rather than raising, always.

        The coercion of the id lives here because four of the callers are cleanup
        blocks, where an `int(None)` would fly out of a `finally` -- one of them
        before the signal handlers are restored, leaving Ctrl-C dead.
        """
        try:
            iid = int(iid)
        except (TypeError, ValueError):
            log(f"WARNING: asked to destroy {iid!r}, which is not an instance "
                f"id -- nothing was killed, and if a machine is running it is "
                f"still billing: books ls")
            return False
        for attempt, pause in enumerate(self.RETRY_S):
            refusal = None
            try:
                self.v.destroy_instance(id=int(iid))
            except Exception as e:
                refusal = e
                # A refusal of access is another trouble and is named as one:
                # after 403 or 429 not this attempt alone is pointless but the
                # `alive` check, which answers "alive" with nobody to ask.
                we_are_refused = any(k in str(e) for k in ("403", "429"))
                log(f"  attempt {attempt+1} to destroy failed: {e}"
                    + ("  -- this is a REFUSAL OF ACCESS, not the machine "
                       "disobeying: waiting longer now, so as not to "
                       "hammer" if we_are_refused else ""))
            time.sleep(pause)
            if not self.alive(iid):
                log(f"instance {iid} DESTROYED, checked -- money has stopped")
                return True
            log(f"  still alive after attempt {attempt+1}"
                + (" (or there is nobody to ask)" if refusal else "")
                + ", repeating")
        log(f"!!! COULD NOT DESTROY {iid} -- YOU ARE STILL BEING CHARGED.\n"
            f"!!! Kill it by hand: vastai destroy instance {iid} -y\n"
            f"!!! or https://cloud.vast.ai/instances/")
        return False

    def reap(self, prefix: str = "bs-") -> int:
        """Clear away whatever our runs left behind."""
        rows = self.v.show_instances()
        mine = [i for i in rows if (i.get("label") or "").startswith(prefix)]
        if not mine:
            log("nothing to clear away")
            return 0
        for i in mine:
            log(f"clearing away {i['id']} ({i.get('label')})")
            self.destroy(int(i["id"]))
        return len(mine)

    def balance(self) -> float:
        return float(self.v.show_user().get("credit") or 0)
