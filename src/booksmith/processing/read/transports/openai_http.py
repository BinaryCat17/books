"""Delivering the question over HTTP: any OpenAI-compatible address.

One transport covers three cases -- vLLM on the rented card over the loopback,
someone else's vLLM or LM Studio, a cloud API with a key -- so the rental is not
a third transport, and nearly the whole paying path is checked at home against
the stand-in server `tests/fake_vlm.py`. `urllib` from the standard library.

A retry is allowed only before the answer: a broken connection, a timeout or a
5xx is repeated, a 200 never, whatever lies in it. `VLM_API_KEY` comes from
`.env` rather than the registry, so the secret cannot ride into `run.json`.
"""
import base64
import json
import os
import time
import urllib.error
import urllib.request

from booksmith.processing.read import Ask, Said, Transport
from booksmith.core import config
from booksmith.core import knobs
from booksmith.core.errors import Refusal

# What counts as a picture. The `data:` type must be the right one: a server
# handed `image/png` over a JPEG answers 400.
MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".webp": "image/webp"}


def _data_uri(path: str) -> tuple[str, int]:
    ext = os.path.splitext(path)[1].lower()
    if ext not in MIME:
        raise ValueError(
            f"{path}: I do not know this image kind. I know {sorted(MIME)}; "
            f"crops are written by `core/raster.py`, and those are .png")
    raw = open(path, "rb").read()
    if not raw:
        raise ValueError(
            f"{path}: the crop is empty (0 bytes). Sending it means getting "
            f"an invented answer to an empty place -- on a blank white sheet "
            f"the model produces tables, five different ones in five tries.")
    return f"data:{MIME[ext]};base64," + base64.b64encode(raw).decode(), len(raw)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect is not followed but declared a refusal.

    `urllib` goes after a 302 itself and carries the `Authorization` header on,
    so the key and the image would reach an address the server named: a
    stranger's answer would be recorded as the reading of our own endpoint.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(
            req.full_url, code,
            f"redirect to {newurl}: not following. The key and the image "
            f"would travel to an address named by the server, not by the "
            f"operator", headers, fp)


_OPENER = urllib.request.build_opener(_NoRedirect)


class _BadBody(Exception):
    """An answer came and there is nothing to parse it with. Not a delivery
    failure."""


def _read_json(req, timeout):
    """The server's answer -> json. Parsing stands apart from delivery.

    A broken body under code 200 is an answer, not a broken connection: inside
    the delivery `try` it would be retried, paying for generation again on the
    very failure that matters most, a long table cut off.
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
        self.timeout = knobs.number("VLM_TIMEOUT_S")
        self.retries = knobs.number("VLM_RETRIES", kind=int)
        # The key is from `.env`, not from the registry: see the header.
        self.key = config.env("VLM_API_KEY")
        if not self.server:
            # A refusal, not a ValueError: the operator sees a line, not a stack.
            raise Refusal(
                "VLM_ENDPOINT is empty: no model address was given. There "
                "is no default on purpose -- a silent `localhost` would make "
                "the run knock at nothing and call that the model's silence.")

    # -------------------------------------------------------- the contract --
    def fingerprint(self) -> dict:
        return {"transport": self.name, "endpoint": self.server,
                "model_asked": self.model,
                "timeout_s": self.timeout, "delivery_retries": self.retries,
                # The key itself is not written: snapshots go to git.
                "api_key": f"present, {len(self.key)} chars" if self.key
                        else "no"}

    def knobs_read(self) -> tuple[str, ...]:
        return ("VLM_ENDPOINT", "MODEL_NAME", "VLM_TIMEOUT_S", "VLM_RETRIES")

    # ------------------------------------------------------------ the ask --
    def check(self, model: str | None = None) -> dict:
        """What exactly this address answers with. Quantities, not "alive".

        Asks the server its name -- an orphan of a previous run answers a health
        check as happily as a fresh one -- and a name that does not match fells
        the run before the first cent. It proves the server, never the weights:
        `vllm serve --served-model-name` makes the server call itself as told,
        and only the reader's fingerprint, taken beside them, proves those.
        """
        want = model or self.model
        try:
            d = _read_json(urllib.request.Request(
                self.server + "/models", headers=_headers(self.key)),
                self.timeout)
        except Exception as e:
            raise Refusal(
                f"the endpoint {self.server} does not answer /models: {e}. "
                f"This is a DELIVERY failure, not the model's silence.") from e
        ids = [m.get("id") for m in (d.get("data") or [])]
        out = {"endpoint": self.server, "models_on_server": ids,
               "asking_for": want, "matched": want in ids}
        if not out["matched"]:
            raise Refusal(
                f"{self.server} carries {ids}, and we are about to ask for "
                f"{want!r}. Counting like this writes one model's name into "
                f"the snapshot over another model's answers -- confidently "
                f"and wrongly.")
        return out

    def send(self, ask: Ask) -> Said:
        """One question. A failure comes back as a value, not as a throw."""
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
                # There was an answer: no repeat, back as a value at once.
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
                # 4xx is our own error in the request: only what can be
                # temporary is repeated.
                if e.code < 500:
                    break
            except Exception as e:
                last = f"{type(e).__name__}: {e}"
            else:
                if not d.get("choices"):
                    # 200 with no choice at all, as a gateway putting its error
                    # in the body answers: not the model keeping silent, which
                    # is an empty string in `content`.
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
                    # As is: a `None` out of the json stays `None`, since "no
                    # field" and "an empty string" are different answers.
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
        # `attempt + 1`, not `self.retries + 1`: a 4xx breaks the loop after one
        # delivery, and the number recorded is the deliveries actually made.
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
        raise Refusal(
            f"VLM_TRANSPORT={name!r}: I know only 'http'. A silent fallback "
            f"to it would make a typo in the transport's name count as a "
            f"successful run.")
    return Http()
