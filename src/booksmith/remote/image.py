"""The rented machine's image: what docker delivers before anything else.

Declared here and not in a model's job spec, because the reader and the layout
detector on a rented card share it: neither job may import the other for the
name of a docker image.
"""
# Delivery tools only (see infra/base/Dockerfile): python, CUDA, torch, vLLM and
# the weights arrive at start through uv, which saturates a link where docker,
# one stream per layer, is capped near 25 Mbit/s.
BASE_IMAGE = "ghcr.io/binarycat17/vast-base:d69de6e"
IMAGE_GB = 0.06
