"""Подставная служба VLM: OpenAI-совместимый адрес, отвечающий по указке.

ЗАЧЕМ. Второй уровень целиком — вырезки, промты, разбор ответа, сборка
страниц, пять разных нулей, слепок — проверяется ЗДЕСЬ, бесплатно, и только
после этого едет на арендованную карту. Прежний второй уровень платил за
отладку разбора аренду за арендой: тринадцать запусков и $0.52, из которых
полезных два, и все ловушки оказались нашими, ни одной модельной.

Сервер отвечает ровно тем, что ему велели: строкой, пустотой, обрывом по
потолку, кодом 500. То есть каждая из пяти бед второго уровня воспроизводится
на месте и за миллисекунды, а не ждёт, когда модель соблаговолит промолчать.

Ни в каком смысле не модель: он не читает картинку и не притворяется, что
читает. Он проверяет НАШУ половину.
"""
import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


class FakeVlm:
    """Служба на случайном порту. `plan` решает, что отвечать.

    `plan` — либо один ответ на все запросы, либо словарь «промт -> ответ»,
    либо функция (промт, картинка) -> ответ. Ответ описывается словарём:

        {"text": "...", "finish": "stop"}   обычный ответ
        {"text": "", "finish": "stop"}      модель промолчала
        {"text": "...", "finish": "length"} оборвано потолком
        {"http": 500}                       отказ доставки
    """

    def __init__(self, plan, model="PaddleOCR-VL-1.6-0.9B"):
        self.plan, self.model = plan, model
        self.seen = []                      # что спрашивали, по порядку
        srv = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):      # тишина в выводе проверок
                pass

            def _json(self, code, body):
                b = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

            def do_GET(self):
                if self.path.endswith("/models"):
                    return self._json(200, {"data": [{"id": srv.model}]})
                return self._json(404, {"error": "нет такого пути"})

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                req = json.loads(self.rfile.read(n) or b"{}")
                content = (req.get("messages") or [{}])[0].get("content") or []
                prompt = next((c.get("text") for c in content
                               if c.get("type") == "text"), "")
                uri = next((c.get("image_url", {}).get("url") for c in content
                            if c.get("type") == "image_url"), "")
                # Байты картинки достаются ЦЕЛИКОМ: проверки сверяют, что до
                # модели доехала та самая вырезка, а не соседняя.
                img = b""
                if "," in uri:
                    img = base64.b64decode(uri.split(",", 1)[1])
                srv.seen.append({"промт": prompt, "байт": len(img),
                                 "модель": req.get("model"),
                                 "порождение": {k: v for k, v in req.items()
                                                if k in ("temperature",
                                                         "max_tokens")}})
                a = srv._answer(prompt, img)
                if "http" in a:
                    return self._json(a["http"], {"error": "подставной отказ"})
                return self._json(200, {
                    "model": srv.model,
                    "choices": [{"message": {"content": a.get("text")},
                                 "finish_reason": a.get("finish", "stop")}],
                    "usage": {"completion_tokens": len(a.get("text") or "")}})

        self.httpd = HTTPServer(("127.0.0.1", 0), H)
        self.port = self.httpd.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}/v1"

    def _answer(self, prompt, img):
        p = self.plan
        if callable(p):
            return p(prompt, img)
        if isinstance(p, dict) and not {"text", "http"} & set(p):
            return p.get(prompt, {"text": ""})
        return p

    def __enter__(self):
        self.t = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.t.start()
        return self

    def __exit__(self, *a):
        self.httpd.shutdown()
        self.httpd.server_close()
