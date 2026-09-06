"""The rented machine's image: what docker delivers before anything else.

Declared here and not in a model's job spec, because two jobs (the reader
and the layout detector on a rented card) share it and the second used to
import the first for two constants -- a layout job importing a reading job
for the name of a docker image.
"""
# The image carries only the delivery tools (see infra/base/Dockerfile);
# python, CUDA, torch, vLLM and the weights are installed at start by
# provision.sh.
#
# Not love of complexity but measurement: docker pulls three layers at once,
# one stream per layer, and the registry cuts a connection to ~25 Mbit/s. A
# 76 Mbit/s ceiling against the machine's 1518 -- a 6.02 GB image rode 10.7
# minutes. The same 11 GB through uv and hf install in 82 seconds: dozens of
# connections, and the channel saturated.
#
# Measured on our side and needing no ground truth: it is about the network,
# not parsing, and so survived the clean slate, unlike the table figures.
BASE_IMAGE = "ghcr.io/binarycat17/vast-base:d69de6e"
IMAGE_GB = 0.06
