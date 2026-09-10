# layout

A layout detector of the tree's own behind the model protocol: one image,
one tag per model. The build arguments name the weights and the adapter;
the weights are baked in, so a start is a pull.

```
docker build -f images/layout/Dockerfile \
  --build-arg MODEL_REPO=PaddlePaddle/PP-DocLayoutV2_onnx --build-arg MODEL_DIR=PP-DocLayoutV2_onnx \
  --build-arg LAYOUT_ADAPTER=doclayout --build-arg LAYOUT_MODEL_NAME=PP-DocLayoutV2 -t model-pp-doclayoutv2 .
docker run --rm -p 8000:8000 model-pp-doclayoutv2
```

Adapters: `doclayout` (PP-DocLayoutV2, V3, plus-L), `yolox`; `docling` and
`docling-egret` need the `docling` extra (`--build-arg EXTRAS=[docling]`).
Knobs from the environment; `BOOKSMITH_SERVE_KEY` sets the bearer key,
`BOOKSMITH_SERVE_KIND` (`layout` or `hybrid`) and `BOOKSMITH_SERVE_KINDS`
declare a hybrid, `PORT` the shim's port. Routes: `schema/openapi/model.yaml`.
Tests: `pytest`.
