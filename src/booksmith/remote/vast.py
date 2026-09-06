"""Renting on vast.ai over the SDK.

This used to parse the CLI's stdout, and half the trouble grew from there:
`destroy instance` asked for confirmation and **returned 0 even when it refused
to work**, so the script reported a destruction while the money kept running.
The SDK asks nothing -- `destroy_instance(id)`. The re-query check stays all
the same: it costs one call, and the mistake costs money.
"""
import os
import re
import time

from vastai import VastAI

from . import pricing
from .spec import HostReq, JobSpec

# ssh on a vast instance hijacks the login into tmux, so `ssh host 'cmd'`
# prints "no sessions" and RUNS NOTHING; cured by this file. rsync goes in at
# once, or fetching results would not be incremental. authorized_keys
# permissions are fixed in a loop, not once: vast writes the file
# world-readable at an undefined moment, sometimes later than our onstart, and
# sshd reads it on every connection. The image does the same through
# StrictModes no, which cannot be relied on: vast caches the built image by
# name and tag, and the machine may hold a build off an older base.
#
# ------------------------------------------------------------ deadman watch
# Destruction used to rest on a live local process -- the `finally` in run_job
# and a guard in its thread. One reboot of the operator's machine and the
# instance lived on billing while its task died with the ssh: instance
# 48131402, seven minutes for nothing.
#
# So the switch moved ONTO the rented machine. vast puts CONTAINER_API_KEY and
# CONTAINER_ID into the container -- the key by which an instance may destroy
# itself -- and a background loop watches the age of /root/.alive, touched
# every 30 seconds by the living operator (Box.start_heartbeat). No touch for
# longer than DEADMAN_GRACE_S and the machine destroys itself.
#
# The grace sits in /root/.alive.grace, not baked into the loop: with --keep
# the instance is deliberately left without an operator and gets another
# number.
DEADMAN_GRACE_S = 900

# Where the watch reports it is ARMED. Without this file nothing could check
# it: on an empty CONTAINER_API_KEY the loop lived as if nothing were wrong and
# knocked `curl -X DELETE` with an empty Bearer every half minute -- the last
# line against a money leak switched off and looking like work, its errors
# going to /root/deadman.log, which we do not fetch. The watch now reports in
# QUANTITIES (pid of its shell, instance id, LENGTH of the key -- the length,
# not the key: the report lies on the machine and travels into our log), and
# `Box.check_deadman` reads it right after ssh, before anything is uploaded.
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
    # The report is written FROM INSIDE the background loop, right before
    # `while`: it testifies not that onstart had the variables but that the
    # watch reached its loop with a non-empty key and id; empty means exit with
    # a shout into the file we read.
    # Its words are LATIN, and that is not style: the string travels to vast
    # through the API, lands as an onstart file, is run by the machine's shell
    # and returns over ssh, and whether UTF-8 survives that can only be checked
    # by renting. A false "watch not armed" would cost the alarm its
    # credibility.
    " if [ -z \"$K\" ] || [ -z \"$I\" ]; then "
    "   echo \"NOT-ARMED key=${{#K}} id='$I'\" > {state}; exit 1; fi; "
    " echo \"ARMED pid=$$ id=$I key=${{#K}} grace={grace}s\" > {state}; "
    " while sleep 30; do "
    # `|| echo` caught only a MISSING file. An empty one (a torn write) gave an
    # empty G and `[ N -gt ]` a syntax error -- that is, a lie: the machine
    # never killed itself and wrote the errors quietly into /root/deadman.log,
    # which we do not fetch.
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


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


class Vast:
    def __init__(self, api_key: str | None = None):
        self.v = VastAI(api_key) if api_key else VastAI()

    # --------------------------------------------------------------- choice
    def offers(self, host: HostReq, image_gb: float, minutes: float,
               payload_gb: float = 0.0, warmup_s: float = 0.0) -> list[dict]:
        q = host.query()
        log(f"поиск: {q}, диск {host.disk_gb} ГБ")
        # `storage` is the disk the server prices `dph_total` AGAINST
        # (`vastai/api/offers.py`: `q["allocated_storage"] = storage`), SDK
        # default 5.0 GiB. We rent 60, and THREE things hang on that number:
        # the server-side `dph_total<max_dph` filter, our budget ceiling and
        # the ledger cost.
        #
        # Measured on the live market 03.09.2026 (RTX_4090, same query, only
        # `storage` differing; 17 offers in BOTH answers): at 60 GiB the price
        # is $0.013…$0.051 an hour higher -- median $0.026, 3.8% (up to 8.4%).
        # The fourfold spread is the host's disk price, $0.16 to $0.53 per
        # GB-month.
        #
        # WHAT IT DID NOT SHOW: the order did not change today -- of 14 shared
        # offers not one moved, the cheapest is the same, so "the ranking
        # picked the wrong machine" is unclaimable. What it did show: those
        # same 3.8% understate the budget ceiling (`Budget` divides money by
        # `dph`), the ledger cost and that server threshold. Of today's 17
        # offers NOT ONE crossed our $0.60 from the disk change -- only one
        # already closer to the ceiling than the surcharge would.
        found = self.v.search_offers(q, order="dph_total",
                                     storage=float(host.disk_gb))
        if not found:
            raise SystemExit(
                f"нет офферов под {host.gpu} дешевле ${host.max_dph}/час.\n"
                "Ослабь --max-dph / --min-down или возьми другую карту.")
        return pricing.rank(found, image_gb, minutes, payload_gb, warmup_s)

    def pick(self, host: HostReq, image_gb: float, minutes: float,
             prefer_machines: list[int] | None = None, show: int = 5,
             payload_gb: float = 0.0, warmup_s: float = 0.0,
             avoid: list[int] | None = None) -> dict:
        ranked = self.offers(host, image_gb, minutes, payload_gb, warmup_s)
        if avoid:
            ranked = [o for o in ranked if o.get("machine_id") not in avoid]
            if not ranked:
                raise SystemExit("годных офферов не осталось: все проверенные "
                                 "машины отсеяны по каналу")
        if prefer_machines:
            # A priority list, not a set: first comes whoever computed fastest
            # for us. This used to take `ranked[0]` of the intersection, the
            # cheapest of the known ones -- and cheap and fast are different
            # machines.
            by_machine = {}
            for o in ranked:
                by_machine.setdefault(o.get("machine_id"), o)
            for pos, mid in enumerate(prefer_machines, 1):
                if mid in by_machine:
                    log(f"машина {mid}: место {pos} в списке предпочтения "
                        f"(по журналу) — берём её")
                    return by_machine[mid]
        log("офферы по полной стоимости прогона:")
        for o in ranked[:show]:
            log("  " + pricing.describe(o))
        return ranked[0]

    # -------------------------------------------------------------- renting
    def create(self, offer_id: int, spec: JobSpec,
               on_created=None) -> int:
        """Create the instance and hand its id out AT ONCE.

        Binding the ssh key, five retries of 4 s, used to live in here. All
        that time the instance already existed and took money while the caller
        did not know its id: Ctrl-C in that window and there was nothing to
        destroy.
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
            # Without this a failed placement silently creates a STOPPED
            # instance that goes on charging for disk.
            cancel_unavail=True,
        )
        iid = res.get("new_contract")
        if not iid:
            raise SystemExit(f"создать инстанс не удалось: {res}")
        log(f"инстанс {iid} создан")
        if on_created:
            on_created(int(iid))       # before all else: it is already billing
        return int(iid)

    def attach_key(self, iid: int, key_path: str) -> bool:
        """A key registered on the account does NOT reach the instance.

        It must be attached to this very instance, or you get `Permission
        denied (publickey)` -- after the image has been downloaded.
        """
        pub = key_path + ".pub"
        if not os.path.exists(pub):
            log(f"  публичного ключа нет в {pub}; надеемся на ключи аккаунта")
            return False
        pubkey = open(pub).read().strip()
        for attempt in range(5):
            try:
                self.v.attach_ssh(instance_id=int(iid), ssh_key=pubkey)
                log("  ssh-ключ привязан к инстансу")
                return True
            except Exception as e:
                if attempt == 4:
                    log(f"  привязать ключ не вышло: {e}")
                time.sleep(4)
        return False

    # --------------------------------------------------------------- status
    def instance(self, iid: int) -> dict | None:
        """The instance description; None only when it surely does not exist.

        On a request error we raise rather than return None: the caller must
        tell "they answered that the machine is gone" from "we could not ask".
        Any 500 or timeout used to look like "no instance", and --reuse took a
        SECOND card while the first billed on to its own watch. Polarity as in
        alive(): unknown is not dead.
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
            inst = self.instance(iid) or {}
            status = inst.get("actual_status")
            msg = (inst.get("status_msg") or "").strip().splitlines()
            note = msg[-1][:90] if msg else ""
            if (status, note) != last:
                log(f"  статус={status} {note}")
                last = (status, note)
            if status == "running":
                return inst
            if status in ("exited", "offline"):
                raise RuntimeError(f"инстанс {iid} умер: {inst.get('status_msg')}")
            time.sleep(10)
        raise RuntimeError(f"инстанс {iid} не поднялся за {timeout:.0f}с")

    def ssh_target(self, iid: int) -> tuple[str, str, str]:
        """The machine's address: direct first, the proxy as fallback.

        `ssh_url` gives out the sshN.vast.ai proxy, and it fails: the tunnel to
        the container sometimes does not come up at all -- "remote port
        forwarding failed for listen port" -- while the direct port answers.
        Direct is also faster: rsync of the result crosses no relay.
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
            raise RuntimeError(f"не разбирается ssh-url: {url!r}")
        log("  прямого адреса нет — иду через прокси vast")
        return m.groups()  # user, host, port

    # ---------------------------------------------------------- destruction
    def alive(self, iid: int) -> bool:
        """Does the instance exist, that is, is money still running."""
        try:
            rows = self.v.show_instances()
        except Exception:
            return True          # could not ask -> assume it is alive
        return any(str(i.get("id")) == str(iid) for i in rows)

    # The backoff GROWS. A flat 4 s pause over five attempts, each making TWO
    # API calls (destroy plus check), is ten requests in twenty seconds:
    # unnoticeable while all is well, but let the API refuse and the code
    # hammers AT THE SAME RATE, answering a rate limit by speeding up. Measured
    # 3 September 2026: after such a burst the key returned 403 to EVERYTHING,
    # `/users/current` included, and `curl` with the same key showed the
    # refusal came from vast.ai, not from our wrapper.
    #
    # The backoffs sum to 2 minutes, deliberately under the deadman grace
    # (900 s): even if destruction fails outright the machine puts itself out.
    RETRY_S = (4, 8, 16, 32, 60)

    def destroy(self, iid: int) -> bool:
        for attempt, pause in enumerate(self.RETRY_S):
            refusal = None
            try:
                self.v.destroy_instance(id=int(iid))
            except Exception as e:
                refusal = e
                # A REFUSAL OF ACCESS IS ANOTHER TROUBLE and must be named as
                # one. "Destroy did not work" means the machine disobeyed; 403
                # and 429 mean we are not let in, and then not only this
                # attempt is pointless but the `alive` check after it -- it
                # will answer "alive" merely because there is nobody to ask.
                we_are_refused = any(k in str(e) for k in ("403", "429"))
                log(f"  попытка {attempt+1} уничтожить не удалась: {e}"
                    + ("  — это ОТКАЗ ДОСТУПА, а не отказ машины: дальше жду "
                       "дольше, чтобы не долбить" if we_are_refused else ""))
            time.sleep(pause)
            if not self.alive(iid):
                log(f"инстанс {iid} УНИЧТОЖЕН, проверено — деньги больше не идут")
                return True
            log(f"  всё ещё жив после попытки {attempt+1}"
                + (" (или спросить некого)" if refusal else "") + ", повторяю")
        log(f"!!! НЕ СМОГ УНИЧТОЖИТЬ {iid} — С ТЕБЯ ПРОДОЛЖАЮТ БРАТЬ ДЕНЬГИ.\n"
            f"!!! Убей вручную: vastai destroy instance {iid} -y\n"
            f"!!! или https://cloud.vast.ai/instances/")
        return False

    def reap(self, prefix: str = "bs-") -> int:
        """Clear away whatever our runs left behind."""
        rows = self.v.show_instances()
        mine = [i for i in rows if (i.get("label") or "").startswith(prefix)]
        if not mine:
            log("подбирать нечего")
            return 0
        for i in mine:
            log(f"подбираю {i['id']} ({i.get('label')})")
            self.destroy(int(i["id"]))
        return len(mine)

    def balance(self) -> float:
        return float(self.v.show_user().get("credit") or 0)
