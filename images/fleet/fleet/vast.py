"""Renting on vast.ai over the SDK"""

import os
import re
import time
from vastai import VastAI
from . import pricing
from .spec import HostReq, JobSpec
from fleet.log import log
from fleet import job
from fleet.errors import Refusal

DEADMAN_GRACE_S = 900
DEADMAN_STATE = "/root/.deadman.state"
ONSTART = "touch /root/.no_auto_tmux; mkdir -p {workdir}; touch /root/.alive; echo {grace} > /root/.alive.grace; (K=$CONTAINER_API_KEY; I=$CONTAINER_ID;  E=/proc/1/environ;  if [ -z \"$K\" ]; then    K=$(tr '\\0' '\\n' < $E | sed -n 's/^CONTAINER_API_KEY=//p' | head -1); fi;  if [ -z \"$I\" ]; then    I=$(tr '\\0' '\\n' < $E | sed -n 's/^CONTAINER_ID=//p' | head -1); fi;  if [ -z \"$K\" ] || [ -z \"$I\" ]; then    echo \"NOT-ARMED key=${{#K}} id='$I'\" > {state}; exit 1; fi;  echo \"ARMED pid=$$ id=$I key=${{#K}} grace={grace}s\" > {state};  while sleep 30; do    G=$(cat /root/.alive.grace 2>/dev/null);    case \"$G\" in ''|0|*[!0-9]*) G={grace};; esac;    A=$(stat -c %Y /root/.alive 2>/dev/null || echo 0);    if [ $(( $(date +%s) - A )) -gt $G ]; then      curl -s -X DELETE -H \"Authorization: Bearer $K\"           https://console.vast.ai/api/v0/instances/$I/ ;    fi;  done) >/root/deadman.log 2>&1 & (for i in $(seq 1 90); do    chmod 700 /root/.ssh 2>/dev/null;    chmod 600 /root/.ssh/authorized_keys 2>/dev/null;    sleep 2;  done) >/dev/null 2>&1 & (command -v rsync >/dev/null ||  (apt-get update -qq && apt-get install -y -qq rsync)) >/tmp/onstart.log 2>&1; sleep infinity"


class Vast:
    def __init__(self, api_key: str | None = None):
        self.v = VastAI(api_key) if api_key else VastAI()

    def offers(
        self,
        host: HostReq,
        image_gb: float,
        minutes: float,
        payload_gb: float = 0.0,
        warmup_s: float = 0.0,
    ) -> list[dict]:
        q = host.query()
        log(f"search: {q}, disk {host.disk_gb} GB")
        found = self.v.search_offers(q, order="dph_total", storage=float(host.disk_gb))
        if not found:
            raise Refusal(
                f"no offers for {host.gpu} under ${host.max_dph}/hour.\nLoosen --max-dph / --min-down or take another card."
            )
        return pricing.rank(found, image_gb, minutes, payload_gb, warmup_s)

    def pick(
        self,
        host: HostReq,
        image_gb: float,
        minutes: float,
        prefer_machines: list[int] | None = None,
        show: int = 5,
        payload_gb: float = 0.0,
        warmup_s: float = 0.0,
        avoid: list[int] | None = None,
    ) -> dict:
        ranked = self.offers(host, image_gb, minutes, payload_gb, warmup_s)
        if avoid:
            ranked = [o for o in ranked if o.get("machine_id") not in avoid]
            if not ranked:
                raise Refusal(
                    "no usable offers left: every machine checked was rejected on channel"
                )
        if prefer_machines:
            by_machine = {}
            for o in ranked:
                by_machine.setdefault(o.get("machine_id"), o)
            for pos, mid in enumerate(prefer_machines, 1):
                if mid in by_machine:
                    log(
                        f"machine {mid}: place {pos} in the preference list (by the ledger) -- taking it"
                    )
                    return by_machine[mid]
        log("offers by the full cost of a run:")
        for o in ranked[:show]:
            log("  " + pricing.describe(o))
        return ranked[0]

    def create(self, offer_id: int, spec: JobSpec, on_created=None) -> int:
        res = self.v.create_instance(
            id=int(offer_id),
            image=spec.image,
            disk=spec.host.disk_gb,
            label=spec.label(),
            env=spec.env or {},
            runtype="ssh_direc ssh_proxy",
            onstart_cmd=ONSTART.format(
                workdir=spec.workdir, grace=DEADMAN_GRACE_S, state=DEADMAN_STATE
            ),
            cancel_unavail=True,
        )
        iid = res.get("new_contract")
        if not iid:
            raise Refusal(f"could not create the instance: {res}")
        log(f"instance {iid} created")
        if on_created:
            on_created(int(iid))
        return int(iid)

    def attach_key(self, iid: int, key_path: str) -> bool:
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

    def instance(self, iid: int) -> dict | None:
        rows = self.v.show_instance(id=int(iid))
        return (
            rows[0] if isinstance(rows, list) and rows else rows if isinstance(rows, dict) else None
        )

    def wait_running(self, iid: int, timeout: float = 2100) -> dict:
        t0, last = (time.time(), None)
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
                raise RuntimeError(f"instance {iid} died: {inst.get('status_msg')}")
            time.sleep(10)
        raise RuntimeError(f"instance {iid} did not come up in {timeout:.0f}s")

    def ssh_target(self, iid: int) -> tuple[str, str, str]:
        inst = self.instance(iid) or {}
        ip = inst.get("public_ipaddr")
        mapped = (inst.get("ports") or {}).get("22/tcp") or []
        port = mapped[0].get("HostPort") if mapped else None
        if ip and port:
            return ("root", str(ip).strip(), str(port))
        url = str(self.v.ssh_url(id=int(iid))).strip()
        m = re.match("ssh://(\\w+)@([\\w\\.\\-]+):(\\d+)", url)
        if not m:
            raise RuntimeError(f"ssh-url does not parse: {url!r}")
        log("  no direct address -- going through the vast proxy")
        return m.groups()

    def alive(self, iid: int) -> bool:
        try:
            rows = self.v.show_instances()
        except Exception:
            return True
        return any((str(i.get("id")) == str(iid) for i in rows))

    RETRY_S = (4, 8, 16, 32, 60)

    def destroy(self, iid) -> bool:
        try:
            iid = int(iid)
        except (TypeError, ValueError):
            log(
                f"WARNING: asked to destroy {iid!r}, which is not an instance id -- nothing was killed, and if a machine is running it is still billing: books ls"
            )
            return False
        for attempt, pause in enumerate(self.RETRY_S):
            refusal = None
            try:
                self.v.destroy_instance(id=int(iid))
            except Exception as e:
                refusal = e
                we_are_refused = any((k in str(e) for k in ("403", "429")))
                log(
                    f"  attempt {attempt + 1} to destroy failed: {e}"
                    + (
                        "  -- this is a REFUSAL OF ACCESS, not the machine disobeying: waiting longer now, so as not to hammer"
                        if we_are_refused
                        else ""
                    )
                )
            time.sleep(pause)
            if not self.alive(iid):
                log(f"instance {iid} DESTROYED, checked -- money has stopped")
                return True
            log(
                f"  still alive after attempt {attempt + 1}"
                + (" (or there is nobody to ask)" if refusal else "")
                + ", repeating"
            )
        log(
            f"!!! COULD NOT DESTROY {iid} -- YOU ARE STILL BEING CHARGED.\n!!! Kill it by hand: vastai destroy instance {iid} -y\n!!! or https://cloud.vast.ai/instances/"
        )
        return False

    def reap(self, prefix: str = "bs-") -> int:
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
