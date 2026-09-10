import json
import time
import urllib.error
import urllib.request
from backend.read import Ask, Said, Transport
from backend import job
from backend import knobs
from backend import protocol as served
from backend.errors import Refusal
from backend.protocol import data_uri as _data_uri


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(
            req.full_url,
            code,
            f"redirect to {newurl}: not following. The key and the image would travel to an address named by the server, not by the operator",
            headers,
            fp,
        )


_OPENER = urllib.request.build_opener(_NoRedirect)


class _BadBody(Exception):
    pass


def _read_json(req, timeout):
    with _OPENER.open(req, timeout=timeout) as r:
        raw = r.read()
    try:
        return json.loads(raw.decode())
    except (ValueError, UnicodeDecodeError) as e:
        raise _BadBody(f"{type(e).__name__}: {e}; first bytes {raw[:120]!r}") from None


def _headers(key, post=False):
    h = {"Authorization": "Bearer " + key} if key else {}
    if post:
        h["Content-Type"] = "application/json"
    return h


class Http(Transport):
    name = "openai-chat"

    def __init__(self, server: str | None = None, model: str | None = None):
        self.server = (server or knobs.knob("VLM_ENDPOINT")).rstrip("/")
        self.model = model or knobs.knob("MODEL_NAME")
        self.timeout = knobs.number("VLM_TIMEOUT_S")
        self.retries = knobs.number("VLM_RETRIES", kind=int)
        self.key = str(job.current().secrets.get("VLM_API_KEY") or "")
        if not self.server:
            raise Refusal(
                "VLM_ENDPOINT is empty: no model address was given. There is no default on purpose -- a silent `localhost` would make the run knock at nothing and call that the model's silence."
            )

    def fingerprint(self) -> dict:
        return {
            "transport": self.name,
            "endpoint": self.server,
            "model_asked": self.model,
            "timeout_s": self.timeout,
            "delivery_retries": self.retries,
            "api_key": f"present, {len(self.key)} chars" if self.key else "no",
        }

    def knobs_read(self) -> tuple[str, ...]:
        return ("VLM_ENDPOINT", "MODEL_NAME", "VLM_TIMEOUT_S", "VLM_RETRIES")

    def check(self, model: str | None = None) -> dict:
        want = model or self.model
        try:
            spoken = served.fetch(
                served.root_of(self.server) + served.DESCRIBE,
                timeout=self.timeout,
                headers=_headers(self.key),
            )
        except served.Unreachable:
            spoken = None
        if spoken is not None:
            d = served.Describe.from_json(spoken)
            name = (d.openai or {}).get("model")
            if d.kind == "layout" or not name:
                raise Refusal(
                    f"{self.server} is a {d.kind} model ({d.label}) "
                    + ("with no chat route" if d.kind == "hybrid" else "")
                    + "; level two asks over the chat route, which a reader serves and a hybrid may. A hybrid without one answers the layout route alone: run a hybrid run."
                )
            out = {
                "endpoint": self.server,
                "models_on_server": [name],
                "asking_for": want,
                "matched": want == name,
                "describe": d.to_json(),
            }
            if not out["matched"]:
                raise Refusal(
                    f"{self.server} describes itself as {d.label} serving {name!r}, and we are about to ask for {want!r}. Counting like this writes one model's name into the snapshot over another model's answers."
                )
            return out
        try:
            d = _read_json(
                urllib.request.Request(self.server + "/models", headers=_headers(self.key)),
                self.timeout,
            )
        except Exception as e:
            raise Refusal(
                f"the endpoint {self.server} does not answer /models: {e}. This is a DELIVERY failure, not the model's silence."
            ) from e
        ids = [m.get("id") for m in d.get("data") or []]
        out = {
            "endpoint": self.server,
            "models_on_server": ids,
            "asking_for": want,
            "matched": want in ids,
        }
        if not out["matched"]:
            raise Refusal(
                f"{self.server} carries {ids}, and we are about to ask for {want!r}. Counting like this writes one model's name into the snapshot over another model's answers -- confidently and wrongly."
            )
        return out

    def send(self, ask: Ask) -> Said:
        uri, nbytes = _data_uri(ask.image)
        body = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": uri}},
                        {"type": "text", "text": ask.prompt},
                    ],
                }
            ],
            **ask.params,
        }
        t0 = time.time()
        last = None
        for attempt in range(max(1, self.retries + 1)):
            try:
                req = urllib.request.Request(
                    self.server + "/chat/completions",
                    method="POST",
                    data=json.dumps(body).encode(),
                    headers=_headers(self.key, post=True),
                )
                d = _read_json(req, self.timeout)
            except _BadBody as e:
                return Said(
                    anchor=ask.anchor,
                    error=f"the response body did not parse: {e}",
                    took_s=time.time() - t0,
                    meta={
                        "delivery_attempts": attempt + 1,
                        "image_bytes": nbytes,
                        "answer_arrived": True,
                        "prompt": ask.prompt,
                        "kind_promised": ask.kind,
                    },
                )
            except urllib.error.HTTPError as e:
                text = e.read().decode(errors="replace")[:400]
                last = f"HTTP {e.code} {e.reason}: {text}".rstrip(": ")
                if e.code < 500:
                    break
            except Exception as e:
                last = f"{type(e).__name__}: {e}"
            else:
                if not d.get("choices"):
                    return Said(
                        anchor=ask.anchor,
                        error=f"200 with no choices: {json.dumps(d)[:200]}",
                        took_s=time.time() - t0,
                        raw=d,
                        meta={
                            "delivery_attempts": attempt + 1,
                            "image_bytes": nbytes,
                            "answer_arrived": True,
                            "prompt": ask.prompt,
                            "kind_promised": ask.kind,
                        },
                    )
                ch = d["choices"][0]
                msg = ch.get("message") or {}
                usage = d.get("usage") or {}
                return Said(
                    anchor=ask.anchor,
                    text=msg.get("content"),
                    finish=ch.get("finish_reason"),
                    took_s=time.time() - t0,
                    tokens=usage.get("completion_tokens"),
                    raw=d,
                    meta={
                        "delivery_attempts": attempt + 1,
                        "image_bytes": nbytes,
                        "model_name_in_answer": d.get("model"),
                        "prompt": ask.prompt,
                        "kind_promised": ask.kind,
                    },
                )
            if attempt + 1 < max(1, self.retries + 1):
                time.sleep(min(2.0 * (attempt + 1), 10.0))
        return Said(
            anchor=ask.anchor,
            error=last or "refused with no reason",
            took_s=time.time() - t0,
            meta={
                "delivery_attempts": attempt + 1,
                "image_bytes": nbytes,
                "prompt": ask.prompt,
                "kind_promised": ask.kind,
            },
        )


def build() -> Transport:
    name = knobs.knob("VLM_TRANSPORT")
    if name != "http":
        raise Refusal(
            f"VLM_TRANSPORT={name!r}: I know only 'http'. A silent fallback to it would make a typo in the transport's name count as a successful run."
        )
    return Http()
