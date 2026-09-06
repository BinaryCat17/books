# vast.ai: traps and measurements

Everything that cost money or hours. Some of it went away with the move from the
CLI to the SDK — marked below.

> **WHAT TO TRUST HERE.** Renting, the network, the image: our own side, no
> ground truth needed. Nothing on the QUALITY of parsing is left — that was
> measured against Mistral OCR, not known text, and cannot be reproduced.
> Contours as measured now: `docs/contour-notes.md`.

## Fixed by moving from the CLI to the SDK

**`destroy instance` asked for confirmation and returned 0 when refused.** The
most expensive trap of all: a non-interactive call printed `Aborted`, exited 0,
the instance kept running, and the script reported it destroyed.
`destroy_instance(id)` in the SDK asks nothing; we kept the verifying re-query
anyway, it costs one call.

**`vastai execute` is no good for arbitrary commands.** Not "another ssh": the
help says "Execute a **(constrained)** remote command", the permitted list is
`ls`, `rm`, `du`, everything else answers `400: Invalid command given`.
Established from the source, not the documentation.

**Parsing stdout instead of structures.** Errors were strings, and the CLI
output format is versioned by nothing.

## Still current

**A key registered on the account never reaches the instance.** `create
ssh-key` puts it in the account only; `attach_ssh` is required for **every**
instance, otherwise `Permission denied (publickey)` — learned after you have
pulled six gigabytes of image.

**sshd forces the login into tmux and swallows the command.** `ssh host
'command'` prints `no sessions / open terminal failed` and runs nothing; cured by
`touch /root/.no_auto_tmux` in onstart.

**Without `cancel_unavail=True` a failed placement leaves a stopped instance**,
still charging for its disk: at the median $0.20 per GB-month, 60 GB is about
$12 a month for nothing.

**`ssh_host` is not always filled in**, while `ssh_url` answers fine; waiting for
it in a loop means hanging silently until the timeout. **Some images have no
`/workspace`** — create your own directory.

**`pkill -f` catches its own shell** and kills the script with code 144. Kill
by a saved PID only.

**There are no network volumes on the market.** `create_network_volume` exists
in the API, `search_network_volumes()` returns **zero offers**; local volumes
are nailed to a physical machine. There will be no persistent weight cache.

## Measurements

| what | value |
|---|---|
| pull from the Baidu registry (Beijing) | 8–14 min |
| pull from the GHCR mirror, slow host | 103 Mbit/s of 990 advertised (10.4%) |
| pull from GHCR, host with a fast disk | ~218 Mbit/s, 2.5 min to start |
| warmed-up machine (`--machine`) | 0.9 min |
| largest layer of the official image | 3.69 GB = 62.4% |
| paddle matmul on an RTX 4090 | 65.5 TFLOP/s |
| traffic price across the RTX 4090 market | $0.4 … $29.3 per TB, median $2.7 |
| disk price | $0.08 … $0.93 per GB-month, median $0.20 |

## What is inside the official image

Read out of the mirror's config blob; history matches the 15 manifest layers
1:1. Three things follow from it, numbered under the table.

| # | compressed | what it is |
|---|---|---|
| 0–7 | 0.49 GB | debian bookworm + Python 3.10.16 + libgl/fonts |
| **8** | **3.69 GB** | `pip install paddlepaddle-gpu==3.2.1`, index **cu126** |
| 9 | 0.20 GB | `paddleocr[doc-parser]==3.6.0` + `paddlex[serving]==3.6.1` |
| **12** | **1.54 GB** | `BUILD_FOR_OFFLINE=true` → weights into `~/.paddlex/official_models` |
| 13–14 | ~0 | `pipeline_config_vllm.yaml`, `pipeline_config_fastdeploy.yaml` |

1. **torch and vllm are absent entirely** — hence the VLM computed in-process.
   Yet `pipeline_config_vllm.yaml` is packed inside and the default CMD expects
   an **external** vLLM server.
2. The 3.69 GB monolith is paddlepaddle-gpu with CUDA 12.6 baked in; the
   `cu126` index explains the missing sm_120 for Blackwell.
3. Weights are 1.54 GB, 26% of the image. Moving them to HF is useful but does
   not by itself cure the cold start.

## What cannot be had at all

We do not control the docker daemon on a rented host, therefore:

- lazy pulling (eStargz, SOCI, nydus) is unavailable — a daemon plugin;
- docker cannot fetch `zstd:chunked` partially;
- there is no parallel fetching **within** a layer in any docker version;
- `max-concurrent-downloads` is a host setting, not ours.

**The only lever available is the layer layout of our own image.**

## Measurement: layout detection on the CPU (2026-08-18)

Superseded by the ONNX section below and kept for its numbers. The temptation:
vLLM computes the VLM on the card, paddle is needed only for layout, so a 186 MB
CPU wheel could replace the 3.69 GB GPU one and halve the image. Measured on
`bench/real/test25.pdf`, 150 dpi, 16 cores, `PP-DocLayoutV2`: 7.59 s/page by
default (68 min for 539 pages), 8.26 with MKLDNN and 8 threads (74 min),
**9.71** with MKLDNN and 16 threads (87 min). Multithreading makes it **worse**,
against ~8 min for the VLM itself on the card.

At $0.378/hour a book costs 71 min = **$0.449** on paddle CPU (5 GB image,
2.7 min delivery, 59 min detection, 8 min VLM) against 15 min = **$0.097** on
paddle GPU (9 GB, 4.9 min, 1 min, 8 min). Four gigabytes of image saved buys an
extra hour of rent, and the conclusion — "GPU build of paddle only" — did not
last long.

## Measurement: the same layout through ONNX Runtime (2026-08-18)

Paddle is not needed for detection at all. PaddlePaddle has **37 official ONNX
repositories** — layout, orientation, PP-OCRv5/v6, formulas — and
`PaddlePaddle/PP-DocLayoutV2_onnx` was updated 10 June, newer than the paddle
weights. For the VL model there is no ONNX at all: GGUF and vLLM only. The
boundary runs between a static graph and autoregressive generation with a KV
cache.

Same processor, same five pages, 82 boxes:

| engine | s/page |
|---|---|
| paddle (CPU) | 8.59 |
| **ONNX Runtime (CPU)** | **2.45** |

Outputs compared by matching boxes through IoU, not by list position — the
engines order them differently, and the naive comparison gave a false 662
pixels:

```
boxes per page:      [25, 20, 6, 19, 12]  in both engines
matched at IoU>0.9:  82/82 (100%)
worst IoU: 1.0000    mean: 1.0000
max coordinate divergence after sorting: 0.00 pixels
```

No divergence whatsoever. Export to ONNX rewrites the graph, it does not
recompute the weights: **in MiB**, the ONNX weights are 204.1 (`inference.onnx`,
213 963 712 bytes) against 203.9 for paddle (`inference.pdiparams` plus
`inference.json`, 213 763 510 bytes). Say the unit: in decimal the same file is
**214 MB**, the figure `CLAUDE.md` quotes for this model — one number, not two.
Matching size proves conversion without quantization; the quantized versions on
HF (uint8) are the ones not to take.

**Conclusion: detection on ONNX Runtime, paddle as a CPU skeleton only.**

| | image | largest layer | CUDA stacks |
|---|---|---|---|
| paddle GPU | ~9 GB | 3.69 GB (41%) | cu126 + cu13 |
| **ONNX** | **~6 GB** | ~1.5 GB (25%) | cu13 only |

`onnxruntime-gpu` 1.29 depends on `nvidia-cuda-runtime~=13.0` and
`nvidia-cudnn-cu13` — the stack torch brings anyway, so two CUDA generations in
one container also go away. Switched on by `engine: onnxruntime` in the
`LayoutDetection` submodule of the paddlex config (a top-level `engine` wins
over it); the config reaches `PaddleOCRVL(paddlex_config=...)` via `**kwargs`.

## Delivery: docker against everything else (measured 2026-08-19)

**Docker is the slowest way to put bytes on a machine**, and its settings
cannot get around that, because the daemon on a rented host is not ours.

| | image through docker | environment around docker |
|---|---|---|
| volume | 6.02 GB | ~11 GB |
| time | 10.7 min | 82 s |
| speed | 76 Mbit/s | ~1100 Mbit/s |

Both rows: RTX 4090, host channel 1518 Mbit/s, NVMe 8166 MB/s. Why 76: docker
pulls three layers at once, exactly one HTTP connection inside a layer, and the
registry throttles the connection. Checked on the same blob: 1 stream —
11 Mbit/s, 3 streams — 31, **exactly threefold**. The connection is throttled,
not the bandwidth. Layer layout hits the same ceiling: splitting 9.2 GB / 46%
into 6.02 GB / 23% doubled the speed and stopped there.

Unpacking is the second misery: layers are applied strictly one at a time, gzip
inside a layer is single-threaded. Nine more minutes passed after "Download
complete", with a disk that does 8166 MB/s — 11 MB/s on compressed input, and
the disk has nothing to do with it.

A 54 MB image comes up in 31 seconds, and the whole design follows from that.
**But 31 s is a measurement of 2026-08-19, not a statement about today**: the
image has grown since, `procps` and `git` went into `infra/base/Dockerfile` on
2026-09-05 (the Dockerfile itself puts git at 20 MB), and there is no docker in
this environment to re-measure with. Re-measure before quoting it as current.

## vast traps found while moving to the thin image

**vast rebuilds any image with a layer of its own carrying ssh**, visible in the
log as a build of `<image>_<tag>/ssh`. Do not keep your own sshd in the image:
our daemon comes up, and vast puts the keys into its own authorized_keys.

**That rebuild is cached by name with tag.** An unchanging `latest` means a
build from an old base stays on the machine forever; the tag must change with
every build — for us, the short commit SHA.

**The key is rejected while the key is correct.** `Permission denied
(publickey)`, and in the container log `Authentication refused: bad ownership or
modes for file /root/.ssh/authorized_keys`: vast writes the file with a foreign
owner (ours was `115:1002`). Cured by `StrictModes no` in the image plus a
background `chmod` from onstart — the second matters, because the first will not
arrive on a machine with a cached rebuild.

**The `sshN.vast.ai` proxy sometimes fails to raise the tunnel**: `remote port
forwarding failed for listen port`, while the direct port answers. We go direct;
the proxy is the fallback.

**Container logs are available through the API** (`v.logs(instance_id=...)`) and
contain sshd output — when ssh will not let you in, the only way to learn why.

## What a clean Debian lacks for this stack

- `libgl1`, `libglib2.0-0` — else `ImportError: libGL.so.1` on importing cv2,
  which paddlex pulls in unconditionally;
- `libgomp1` — OpenMP for numpy and paddle;
- `gcc`, `g++`, `libc6-dev` — triton and flashinfer compile kernels on the fly,
  and gcc alone is not enough: the kernels are C++, nvcc dies on `cannot execute
  cc1plus`;
- `CUDA_HOME` — flashinfer looks for CUDA through it, else under
  `/usr/local/cuda`, which does not exist: CUDA arrives in wheels
  (`nvidia/cu13/bin/nvcc`).

## Seams between vLLM and paddleocr

**`vl_rec_server_url` switches nothing by itself.** It also needs
`vl_rec_backend="vllm-server"`, otherwise the pipeline builds a local VL model
and dies on `gpu:0`, our paddle being a CPU build.

**`paddlex_config` as a dict replaces the configuration whole; it does not
merge.** In `paddleocr/_pipelines/base.py` this is literally `config =
self._paddlex_config`. One submodule cannot be passed — the pipeline would be
left without `pipeline_name`. Load the config yourself through
`load_pipeline_config("PaddleOCR-VL-1.6")` and merge your submodule into it.

**flashinfer fails to build the sampler**: the `nvidia-cuda-nvcc` wheel arrives
as 13.3, torch is built for CUDA 13.0, and the cccl headers catch it. Simpler to
switch off: `VLLM_USE_FLASHINFER_SAMPLER=0` — which also removes kernel
compilation from the startup.

**vLLM takes 90% of video memory by default**, leaving none for layout
detection: ONNX Runtime dies on `Failed to allocate memory`. We set 0.75.

**vLLM startup time varies sixfold between machines** — 65 s against 374 s on
identical RTX 4090s. Neither channel nor disk explains it: the time is spread
across imports, compilation and warm-up, i.e. across the host's processor.

## Unruled tables: a detection threshold, not the model

Symptom: three blocks that look alike on one page, all "RECOMMENDED STANDARDS",
and only one comes out as a table. The layout JSON says why — the detector
labelled them `table 0.70`, `text 0.78`, `text 0.61`. The table was not missed;
it lost to text on confidence. RT-DETR proposes several candidates of different
classes for one region, and `table` is class 21 in PP-DocLayoutV2. Confirmed
again on the current bench: for four of the misses the correct box lies in the
raw output below threshold.

We do not tune the threshold ourselves — the registry holds the weights' own
0.5. What stands instead is the sweep over six synthetic books with exact ground
truth, replayed from the same model's saved raw output: 0.5 finds 83 artefacts
of 110, 0.25 finds 92 at the price of seven extra boxes, below 0.1 only the
extras grow (`docs/contour-notes.md`).

Changing the detector was called risky here because PaddleOCR-VL leans on the
PP-DocLayoutV2 taxonomy — 25 classes including `display_formula`,
`inline_formula`, `vision_footnote`, which DocLayout-YOLO, Docling heron and
Surya lack, so the mapping would have to be written by hand. It has been written
since: `src/booksmith/policy.py` carries five vocabularies (25 names for V2, 20
for plus-L, 17 each for heron and egret, 11 for DocLayNet), and `books detect`
picks between six detectors by one knob.

Separately: PP-DocLayout_plus-L is NOT an improvement on PP-DocLayoutV2 — it is
the other way round. V2 is built on top of plus-L: its RT-DETR-L detector is
initialized from plus-L weights, with a six-layer transformer pointer network
added on top for reading order.
