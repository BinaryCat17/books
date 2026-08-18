#!/usr/bin/env python3
"""Run a PDF through Mistral's OCR API and write Markdown + extracted images.

    ./mistral_ocr.py some.pdf out_dir/ [--model mistral-ocr-latest]

Reads MISTRAL_API_KEY from .env at the project root (or the environment).  Uploads the file,
asks for OCR with embedded images, then writes:

    out_dir/<stem>.md        markdown, image links rewritten to local files
    out_dir/images/*.png     images the API extracted, with their bboxes
    out_dir/raw.json         the untouched API response, for inspection

The API caps uploads at 50 MB / 1000 pages, so split larger books first.
"""
import base64
import json
import os
import sys
import time

import requests

API = "https://api.mistral.ai/v1"


def load_key():
    """Ключ читается из .env в корне проекта — см. booksmith.config."""
    from booksmith.config import require
    return require("MISTRAL_API_KEY")["MISTRAL_API_KEY"]


def upload(key, path):
    """Upload the PDF and return a short-lived signed URL for it."""
    with open(path, "rb") as f:
        r = requests.post(
            f"{API}/files",
            headers={"Authorization": f"Bearer {key}"},
            files={"file": (os.path.basename(path), f, "application/pdf")},
            data={"purpose": "ocr"},
            timeout=600,
        )
    r.raise_for_status()
    fid = r.json()["id"]
    r = requests.get(f"{API}/files/{fid}/url", params={"expiry": 24},
                     headers={"Authorization": f"Bearer {key}"}, timeout=60)
    r.raise_for_status()
    return fid, r.json()["url"]


def run_ocr(key, url, model):
    payload = {
        "model": model,
        "document": {"type": "document_url", "document_url": url},
        "include_image_base64": True,
    }
    r = requests.post(f"{API}/ocr", headers={
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }, json=payload, timeout=1800)
    if r.status_code >= 400:
        sys.exit(f"OCR failed [{r.status_code}]: {r.text[:800]}")
    return r.json()


def save(result, out_dir, stem):
    img_dir = os.path.join(out_dir, "images")
    os.makedirs(img_dir, exist_ok=True)
    with open(os.path.join(out_dir, "raw.json"), "w") as f:
        json.dump(result, f, indent=1)

    md, n_img = [], 0
    for page in result.get("pages", []):
        idx = page.get("index", 0)
        text = page.get("markdown", "")
        for im in page.get("images", []):
            b64 = im.get("image_base64") or ""
            if not b64:
                continue
            if "," in b64[:64]:                      # strip data: prefix
                b64 = b64.split(",", 1)[1]
            name = f"p{idx:04d}_{im['id']}"
            if not name.lower().endswith((".png", ".jpg", ".jpeg")):
                name += ".png"
            with open(os.path.join(img_dir, name), "wb") as f:
                f.write(base64.b64decode(b64))
            text = text.replace(f"]({im['id']})", f"](images/{name})")
            n_img += 1
        md.append(f"\n<!-- page {idx + 1} -->\n\n{text}")

    path = os.path.join(out_dir, stem + ".md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    return path, n_img


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) < 2:
        print(__doc__)
        return 1
    pdf, out_dir = args[0], args[1]
    model = "mistral-ocr-latest"
    for a in sys.argv[1:]:
        if a.startswith("--model"):
            model = a.split("=", 1)[1] if "=" in a else sys.argv[sys.argv.index(a) + 1]
    os.makedirs(out_dir, exist_ok=True)

    key = load_key()
    t0 = time.time()
    print(f"uploading {os.path.basename(pdf)} ({os.path.getsize(pdf)/1e6:.1f} MB)...")
    fid, url = upload(key, pdf)
    print(f"  file id {fid}, {time.time()-t0:.0f}s")

    print(f"running OCR with {model}...")
    result = run_ocr(key, url, model)
    print(f"  done in {time.time()-t0:.0f}s")

    stem = os.path.splitext(os.path.basename(pdf))[0]
    path, n_img = save(result, out_dir, stem)
    print(f"pages: {len(result.get('pages', []))}, images: {n_img}")
    print("usage:", json.dumps(result.get("usage_info", {})))
    print("wrote", path)

    requests.delete(f"{API}/files/{fid}",
                    headers={"Authorization": f"Bearer {key}"}, timeout=60)
    print("uploaded file deleted from Mistral")
    return 0


if __name__ == "__main__":
    sys.exit(main())
