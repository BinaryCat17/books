"""The model side of the protocol: a model of the tree's own behind the
three routes of `core/served.py`.

`layout` puts a `Detector` behind describe, health and layout; `vlm` puts a
vLLM behind describe and health and passes its chat route through unchanged.
Both are the standard library's threading server, as the stand-ins under
`tests/` are: three routes and a pass-through need no framework, and the
image that carries a detector carries the detect extra and nothing more.
Nothing here repairs, re-asks or edits what the model returns; a request is
answered once, and a failure is a status with the reason.
"""
