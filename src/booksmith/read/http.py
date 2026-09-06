"""Delivering the question over HTTP: any OpenAI-compatible address.

One transport covers three cases, and that is not a coincidence but the
reason for choosing this protocol:

    vLLM on the rented card   http://127.0.0.1:8118/v1  -- the code we run home
    someone's vLLM / LM Studio   http://host:port/v1
    a cloud API with a key       https://.../v1, the key out of `.env`

HENCE THE MAIN PROPERTY: the rental is NOT a third transport. On the box
`run.sh` raises vLLM on the loopback, and the same command with the same code
goes there. So nearly the whole paying path is checked at home for free,
against the stand-in server `tests/fake_vlm.py`, and only the checked rides to
the card. The previous level two paid for debugging its parsing rental by
rental: thirteen launches, $0.52, two useful.

`urllib` from the standard library, not `requests` and not `openai`. Decided
already: `pyproject.toml` dropped `requests` saying "HTTP in live code goes
through urllib". The `openai` client would add a dependency for fifty lines,
and one more place for a retry to hide in.

A RETRY IS ALLOWED ONLY BEFORE THE ANSWER. A broken connection, a timeout, a
5xx -- we repeat: there was no answer at all, and the second question is the
first one. A 200 IS NEVER REPEATED, whatever lies in it: emptiness, a stump,
nonsense. Asking again after an answer is repairing the model; the project
rule forbids it, and here the ban is expressed in code, not promised in a
comment.

THE KEY DOES NOT RIDE INTO THE SNAPSHOT. `VLM_API_KEY` is read through
`config.env`, that is from `.env`, and not through the knob registry:
everything declared a knob lands in `run.json` by value, and the secret would
ride into a file that goes to git. The fingerprint holds only the fact of it
and its length.
"""
import base64
import json
import os
import time
import urllib.error
import urllib.request

from . import Ask, Said, Transport
from .. import config
from ..run import knobs

# What counts as a picture. The list is declared because a `data:` string
# must carry the right type: a server handed `image/png` over a JPEG answers
# 400, and working that out on the rented card is expensive.
MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".webp": "image/webp"}


def _data_uri(path: str) -> tuple[str, int]:
    ext = os.path.splitext(path)[1].lower()
    if ext not in MIME:
        raise ValueError(
            f"{path}: I do not know this image kind. I know {sorted(MIME)}; "
            f"crops are written by `doc/crop.py`, and those are .png")
    raw = open(path, "rb").read()
    if not raw:
        raise ValueError(
            f"{path}: the crop is empty (0 bytes). Sending it means getting "
            f"an invented answer to an empty place -- on a blank white sheet "
            f"the model produces tables, five different ones in five tries.")
    return f"data:{MIME[ext]};base64," + base64.b64encode(raw).decode(), len(raw)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect is NOT followed but declared a refusal.

    The measurement this class exists for: `urllib` goes after a 302 itself,
    and the server that answered leads the request wherever it likes. The
    `Authorization` header rides ON -- `VLM_API_KEY` goes to an address the
    operator did not name; the POST turns into a GET, the picture is lost, and
    a stranger's invention comes back with `finish="stop"` and is recorded as
    the reading, the snapshot naming OUR address.

    There is no reason to follow: the operator sets the model's address by a
    knob, and swapping it in flight is not a convenience but a swapped run.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(
            req.full_url, code,
            f"redirect to {newurl}: not following. The key and the image "
            f"would travel to an address named by the server, not by the "
            f"operator", headers, fp)


_OPENER = urllib.request.build_opener(_NoRedirect)


class _BadBody(Exception):
    """An answer came and there is nothing to parse it with. NOT a delivery
    failure."""


def _read_json(req, timeout):
    """The server's answer -> json. Parsing is SEPARATED from delivery on
    purpose.

    A broken body under code 200 is an ANSWER, not a broken connection (see
    the header). `json.loads` used to stand inside the common `try`, and
    `JSONDecodeError` fell into the delivery-failure branch -- measured: a
    broken body, an empty body and a truncated body each gave THREE calls to
    the service at `VLM_RETRIES=2`, that is triple payment for generation on
    exactly the failure the project fears (a long table cut off).
    """
    with _OPENER.open(req, timeout=timeout) as r:
        raw = r.read()
    try:
        return json.loads(raw.decode())
    except (ValueError, UnicodeDecodeError) as e:
        raise _BadBody(f"{type(e).__name__}: {e}; first bytes "
                       f"{raw[:120]!r}") from None


def _headers(key, post=False):
    h = {"Authorization": "Bearer " + key} if key else {}
    if post:
        h["Content-Type"] = "application/json"
    return h


class Http(Transport):
    """An OpenAI-compatible address. All it knows of the model is its name."""

    name = "openai-chat"

    def __init__(self, server: str | None = None, model: str | None = None):
        self.server = (server or knobs.knob("VLM_ENDPOINT")).rstrip("/")
        self.model = model or knobs.knob("MODEL_NAME")
        self.timeout = float(knobs.knob("VLM_TIMEOUT_S"))
        self.retries = int(knobs.knob("VLM_RETRIES"))
        # The key is from `.env`, not from the registry: see the header.
        self.key = config.env("VLM_API_KEY")
        if not self.server:
            # SystemExit, not ValueError: the operator must see a LINE, not a
            # stack down to `sys.exit(main())`. The rest of the CLI answers
            # such trouble exactly so (`books html` on a swapped PDF,
            # `parse_pages`).
            raise SystemExit(
                "VLM_ENDPOINT is empty: no model address was given. There "
                "is no default on purpose -- a silent `localhost` would make "
                "the run knock at nothing and call that the model's silence.")

    # -------------------------------------------------------- the contract --
    def fingerprint(self) -> dict:
        return {"transport": self.name, "endpoint": self.server,
                "model_asked": self.model,
                "timeout_s": self.timeout, "delivery_retries": self.retries,
                # The key itself is NOT written: snapshots go to git.
                "api_key": ("present, %d chars" % len(self.key)) if self.key
                        else "no"}

    def knobs_read(self) -> tuple[str, ...]:
        return ("VLM_ENDPOINT", "MODEL_NAME", "VLM_TIMEOUT_S", "VLM_RETRIES")

    # ------------------------------------------------------------ the ask --
    def check(self, model: str | None = None) -> dict:
        """What exactly this address answers with. Quantities, not "alive".

        What for: the health check `curl /v1/models` in `run.sh` was answered
        by an ORPHAN of the previous run holding 60% of the video memory, and
        the script decided it had raised the server itself. What is asked here
        is not "are you alive" but "WHAT IS YOUR NAME", and a name that does
        not match fells the run before the first cent.

        WHAT THIS CHECK CANNOT DO, and keeping quiet about it is not allowed:
        `vllm serve --served-model-name` makes the server call itself AS
        TOLD, not after the weights on disk. A matching name proves we reached
        our own server, not that the promised weights lie under it. Only the
        reader's fingerprint, taken beside them, proves those.
        """
        want = model or self.model
        try:
            d = _read_json(urllib.request.Request(
                self.server + "/models", headers=_headers(self.key)),
                self.timeout)
        except Exception as e:            # noqa: BLE001 -- any failure is one
            raise RuntimeError(
                f"the endpoint {self.server} does not answer /models: {e}. "
                f"This is a DELIVERY failure, not the model's silence.") from e
        ids = [m.get("id") for m in (d.get("data") or [])]
        out = {"endpoint": self.server, "models_on_server": ids,
               "asking_for": want, "matched": want in ids}
        if not out["matched"]:
            raise RuntimeError(
                f"{self.server} carries {ids}, and we are about to ask for "
                f"{want!r}. Counting like this writes one model's name into "
                f"the snapshot over another model's answers -- confidently "
                f"and wrongly.")
        return out

    def send(self, ask: Ask) -> Said:
        """One question. A failure comes back as a VALUE, not as a throw."""
        uri, nbytes = _data_uri(ask.image)
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": uri}},
                {"type": "text", "text": ask.prompt}]}],
            **ask.params,
        }
        t0 = time.time()
        last = None
        # Only a delivery failure is repeated, and only before an answer.
        for attempt in range(max(1, self.retries + 1)):
            try:
                req = urllib.request.Request(
                    self.server + "/chat/completions", method="POST",
                    data=json.dumps(body).encode(),
                    headers=_headers(self.key, post=True))
                d = _read_json(req, self.timeout)
            except _BadBody as e:
                # THERE WAS AN ANSWER. No repeat -- back as a value at once.
                return Said(anchor=ask.anchor,
                            error=f"the response body did not parse: {e}",
                            took_s=time.time() - t0,
                            meta={"delivery_attempts": attempt + 1,
                                  "image_bytes": nbytes,
                                  "answer_arrived": True,
                                  "prompt": ask.prompt, "kind_promised": ask.kind})
            except urllib.error.HTTPError as e:
                text = e.read().decode(errors="replace")[:400]
                # `e.reason` is required: the redirect refusal has an empty
                # body, and without the reason the operator would see a bare
                # "HTTP 302:".
                last = f"HTTP {e.code} {e.reason}: {text}".rstrip(": ")
                # 4xx is our own error in the request: repeating it is
                # pointless and paid for. We repeat only what can be temporary.
                if e.code < 500:
                    break
            except Exception as e:        # noqa: BLE001 -- break, timeout, DNS
                last = f"{type(e).__name__}: {e}"
            else:
                if not d.get("choices"):
                    # The server answered 200 and gave no choice at all (so do
                    # gateways that put the error in the body). NOT the model
                    # keeping silent: silence is an empty string in `content`.
                    return Said(
                        anchor=ask.anchor,
                        error=f"200 with no choices: {json.dumps(d)[:200]}",
                        took_s=time.time() - t0, raw=d,
                        meta={"delivery_attempts": attempt + 1,
                              "image_bytes": nbytes, "answer_arrived": True,
                              "prompt": ask.prompt, "kind_promised": ask.kind})
                ch = d["choices"][0]
                msg = ch.get("message") or {}
                usage = d.get("usage") or {}
                return Said(
                    anchor=ask.anchor,
                    # `content` is taken as is. A `None` out of the json stays
                    # `None`: "there was no field" and "an empty string" are
                    # different answers.
                    text=msg.get("content"),
                    finish=ch.get("finish_reason"),
                    took_s=time.time() - t0,
                    tokens=usage.get("completion_tokens"),
                    raw=d,
                    meta={"delivery_attempts": attempt + 1,
                          "image_bytes": nbytes,
                          "model_name_in_answer": d.get("model"),
                          "prompt": ask.prompt, "kind_promised": ask.kind})
            if attempt + 1 < max(1, self.retries + 1):
                time.sleep(min(2.0 * (attempt + 1), 10.0))
        # `attempt + 1`, NOT `self.retries + 1`. A 4xx breaks the loop after one
        # delivery, and the constant recorded three of them in the snapshot --
        # a run that asked once was written down as having asked three times,
        # and nothing anywhere would have contradicted it. Every other return
        # path in this function already counts the truth.
        return Said(anchor=ask.anchor, error=last or "refused with no reason",
                    took_s=time.time() - t0,
                    meta={"delivery_attempts": attempt + 1,
                          "image_bytes": nbytes,
                          "prompt": ask.prompt, "kind_promised": ask.kind})


def build() -> Transport:
    """The transport by the knob registry. There is exactly one; the name is
    compared to it so an unknown one falls out loud instead of quietly
    becoming `http`."""
    name = knobs.knob("VLM_TRANSPORT")
    if name != "http":
        raise SystemExit(
            f"VLM_TRANSPORT={name!r}: I know only 'http'. A silent fallback "
            f"to it would make a typo in the transport's name count as a "
            f"successful run.")
    return Http()
