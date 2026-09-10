# vlm

PaddleOCR-VL behind the model protocol: vLLM raised as a subprocess, describe
and health beside it, the chat route passed through unchanged. The weights
are baked into the image and hashed once at build.

```
docker build -f images/vlm/Dockerfile -t model-paddleocr-vl .
docker run --rm --gpus all -p 8000:8000 model-paddleocr-vl
```

Environment: `MODEL_NAME`, `VL_MODEL_DIR`, `VLM_TIMEOUT_S`, `PORT` (vLLM's),
`BOOKSMITH_PORT` (the shim's), `BOOKSMITH_UPSTREAM` (a vLLM already up,
instead of raising one), `BOOKSMITH_LOG_DIR` (writable), `BOOKSMITH_SERVE_KEY`. Routes: `schema/openapi/model.yaml`. Tests: `pytest`.
