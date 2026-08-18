#!/usr/bin/env python3
"""Runs INSIDE the instance: PDF -> markdown + images via PaddleOCR-VL.

`restructure_pages` is the part worth having — it merges tables that continue
onto the next page and concatenates paragraphs across the page break, which is
exactly the stitching we hand-rolled for the PyMuPDF pipeline.
"""
import argparse
import json
import os
import sys
import time


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="PaddleOCR-VL-1.6-0.9B")
    ap.add_argument("--server", default="", help="VLM service URL; empty = in-process")
    ap.add_argument("--device", default="gpu:0",
                    help="paddle device; without this the pipeline ran wholly on "
                         "CPU (GPU sat at 0%% while one core pegged)")
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    from paddleocr import PaddleOCRVL

    kwargs = {"device": a.device}
    if a.server:
        kwargs.update(vl_rec_server_url=a.server, vl_rec_api_model_name=a.model)
        print(f"using VLM service at {a.server}", flush=True)
    else:
        print(f"using in-process VLM on {a.device}", flush=True)

    t0 = time.time()
    try:
        pipeline = PaddleOCRVL(**kwargs)
    except TypeError:                       # older signature without `device`
        kwargs.pop("device")
        print("pipeline does not accept device=, falling back", flush=True)
        pipeline = PaddleOCRVL(**kwargs)
    print(f"pipeline ready in {time.time()-t0:.0f}s", flush=True)

    t1 = time.time()
    pages = list(pipeline.predict(a.pdf))
    n = len(pages)
    dt = time.time() - t1
    print(f"parsed {n} pages in {dt:.0f}s ({n/max(dt,1):.2f} pages/s)", flush=True)

    # Cross-page stitching.  Older builds lack it; degrade rather than fail.
    try:
        results = pipeline.restructure_pages(
            pages, merge_tables=True, concatenate_pages=True)
        print("restructure_pages: on (tables merged, pages concatenated)", flush=True)
    except (AttributeError, TypeError) as e:
        print(f"restructure_pages unavailable ({e}); saving per page", flush=True)
        results = pages

    md_dir = os.path.join(a.out, "markdown")
    js_dir = os.path.join(a.out, "json")
    os.makedirs(md_dir, exist_ok=True)
    os.makedirs(js_dir, exist_ok=True)
    for res in results:
        try:
            res.save_to_markdown(save_path=md_dir)
        except Exception as e:
            print(f"  save_to_markdown failed: {e}", flush=True)
        try:
            res.save_to_json(save_path=js_dir)
        except Exception as e:
            print(f"  save_to_json failed: {e}", flush=True)

    with open(os.path.join(a.out, "run.json"), "w") as f:
        json.dump({"pages": n, "seconds": round(dt, 1),
                   "pages_per_sec": round(n / max(dt, 1), 3),
                   "server": bool(a.server), "model": a.model}, f, indent=1)
    print(f"wrote {a.out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
