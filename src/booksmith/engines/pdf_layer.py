#!/usr/bin/env python3
"""Turn a scanned, OCR'd book PDF into Markdown.

Written for two-column technical books scanned by the Internet Archive (their
PDFs already carry an OCR text layer, so no OCR pass is needed here).

    ./pdf_to_markdown.py raw/some_book.pdf            # -> processed/some_book/
    ./pdf_to_markdown.py raw/some_book.pdf --no-images
    FIRST=30 LAST=48 ./pdf_to_markdown.py raw/some_book.pdf   # page range, for tuning

What it does beyond a plain text dump:
  * reads the two columns in the right order, and keeps centred page headers
    (which straddle the gutter) out of the column flow;
  * rejoins paragraphs the OCR chopped in half, including across page breaks,
    and undoes end-of-line hyphenation;
  * promotes "Chapter N" / "Sec. N.M" lines to Markdown headings, preferring
    chapter titles from the book's own table of contents (display type OCRs
    badly, the contents page does not);
  * italicises "Fig. / PLATE / Table" captions;
  * drops page-number folios, recording them in `<!-- pdf page N | printed
    page M -->` markers instead;
  * crops figure artwork out of the page scans into images/ and links it in
    place (page scans are single MRC images, so figures cannot be pulled out
    as embedded images -- the blank bands between text lines are rendered).

Layout constants below are tuned for ~506pt-wide pages; adjust for other books.
"""
import os
import re
import sys
import pymupdf

BAND = 10.0             # half-width of the gutter test band
WIDE_FRAC = 0.49        # a line this fraction of page width spans both columns
FIG_MIN_H = 55.0        # a vertical gap this tall in a column may hold artwork
FIG_DPI = 150
TOP_MARGIN, BOT_MARGIN = 30.0, 45.0   # live text area, from the page edges


class Layout:
    """Per-document page geometry."""

    def __init__(self, doc):
        r = doc[0].rect
        self.gutter = r.width / 2
        self.wide = r.width * WIDE_FRAC
        self.top = TOP_MARGIN
        self.bot = r.height - BOT_MARGIN
        self.width = r.width


# ---------------------------------------------------------------- extraction

def page_lines(page, L):
    """Return ([(block_no, column, bbox, text, size)], two_col) for one page.

    column is 0 (left), 1 (right) or -1 (centred header, sorts first).
    """
    d = page.get_text("dict")
    raw = []
    for b in d["blocks"]:
        if b["type"] != 0:
            continue
        for l in b["lines"]:
            spans = [s for s in l["spans"] if s["text"].strip()]
            if spans:
                raw.append((b["number"], spans, l["bbox"]))

    # A page is single-column only if wide lines genuinely carry text across
    # the gutter.  Centred headings and folios touch the gutter but are short,
    # and the OCR sometimes merges two columns into one line with a hole in
    # the middle -- neither means single-column.
    full_width = 0
    for _, spans, bbox in raw:
        if bbox[2] - bbox[0] < L.wide:
            continue
        if any(s["bbox"][0] < L.gutter + BAND and s["bbox"][2] > L.gutter - BAND
               for s in spans):
            full_width += 1
    two_col = len(raw) > 4 and full_width <= max(2, 0.05 * len(raw))

    out = []
    for bno, spans, bbox in raw:
        if not two_col:
            out.append((bno, 0, bbox, join_spans(spans), max_size(spans)))
            continue
        if bbox[0] < L.gutter < bbox[2] and bbox[2] - bbox[0] < L.wide:
            out.append((bno, -1, bbox, join_spans(spans), max_size(spans)))
            continue
        left = [s for s in spans if (s["bbox"][0] + s["bbox"][2]) / 2 < L.gutter]
        right = [s for s in spans if (s["bbox"][0] + s["bbox"][2]) / 2 >= L.gutter]
        for col, grp in ((0, left), (1, right)):
            if grp:
                bb = [s["bbox"] for s in grp]
                gb = (min(x[0] for x in bb), min(x[1] for x in bb),
                      max(x[2] for x in bb), max(x[3] for x in bb))
                out.append((bno, col, gb, join_spans(grp), max_size(grp)))
    return out, two_col


def join_spans(spans):
    spans = sorted(spans, key=lambda s: s["bbox"][0])
    txt = ""
    for s in spans:
        t = s["text"]
        if txt and not txt.endswith(" ") and not t.startswith(" "):
            txt += " "
        txt += t
    return re.sub(r"\s+", " ", txt).strip()


def max_size(spans):
    return max(s["size"] for s in spans)


# ---------------------------------------------------------------- text fixes

def glue(prev, nxt):
    """Join two OCR'd lines, undoing end-of-line hyphenation."""
    if prev.endswith(("¬", "-", "‐", "—")) and nxt[:1].islower():
        return prev[:-1] + nxt
    if prev.endswith("¬"):
        return prev[:-1] + nxt
    return prev + " " + nxt


def clean(t):
    t = t.replace("¬", "-")
    t = t.replace("^^", '"').replace("''", '"').replace("``", '"')
    t = re.sub(r"[‘’‛´`]", "'", t)
    t = re.sub(r"[“”]", '"', t)
    t = re.sub(r"\s+([,.;:])", r"\1", t)
    t = re.sub(r"\s{2,}", " ", t)
    return t.strip()


# ---------------------------------------------------------------- structure

RE_CHAPTER = re.compile(r"^Chapter\s+([0-9]{1,2})\b\s*(.*)$", re.I)
RE_SEC = re.compile(r"^Sec[.,;:^]{0,2}\s*(\d{1,2})\s*[.,:;^]\s*(\d{1,2})\b\.?\s*(.*)$", re.I)
RE_PAGENO = re.compile(r"^[ivxlcdm]{1,7}$|^\d{1,3}$", re.I)
RE_CAPTION = re.compile(r"^(Fig|PLATE|Plate|Table)\b\.?\s*\d", re.I)
RE_ENDS_SENTENCE = re.compile(r"[.!?:;\"')\]]$")

SMALL = {"of", "and", "the", "a", "an", "to", "in", "on", "for", "with", "by", "or"}


def titlecase(s):
    out = []
    for i, w in enumerate(s.split()):
        lw = w.lower()
        out.append(lw if (i and lw in SMALL) else (lw[:1].upper() + lw[1:]))
    return " ".join(out)


def is_page_number(text, bbox, L):
    return bool(RE_PAGENO.match(text.strip())) and (bbox[1] > L.bot - 28 or bbox[3] < 45)


def classify(text):
    """Return (kind, value). Kinds: chapter, sec, caption, head, body."""
    t = clean(text)
    if not t:
        return None, ""
    m = RE_CHAPTER.match(t)
    if m and len(t) < 80:
        return "chapter", (m.group(1), m.group(2).strip(" .-"))
    m = RE_SEC.match(t)
    if m:
        return "sec", (f"{m.group(1)}.{m.group(2)}", m.group(3).strip(" ."))
    if RE_CAPTION.match(t):
        return "caption", t
    letters = [c for c in t if c.isalpha()]
    upper = (sum(c.isupper() for c in letters) / len(letters)) if letters else 0
    if len(t) < 75 and upper > 0.8 and len(letters) > 3:
        return "head", titlecase(t)
    return "body", t


def toc_titles(doc, scan_pages=8):
    """Chapter titles lifted from the book's own table of contents."""
    fixes = {"RecondHioning": "Reconditioning", "Sliues": "Slides"}
    titles = {}
    for pno in range(min(scan_pages, doc.page_count)):
        text = doc[pno].get_text()
        if "CONTENTS" not in text.upper():
            continue
        for line in text.splitlines():
            m = re.match(r"^\s*(\d{1,2})\.\s+([A-Za-z][^.]*?)\s*[.\s]*\s*\d{1,3}\s*$", line)
            if m:
                t = m.group(2).strip()
                for bad, good in fixes.items():
                    t = t.replace(bad, good)
                titles.setdefault(int(m.group(1)), t)
    return titles


# ---------------------------------------------------------------- figures

def crop_figures(page, lines, two_col, pageno, L, img_dir):
    """Render the blank bands inside each column that hold artwork."""
    results = []
    cols = (((0, 42.0, L.gutter - 2), (1, L.gutter + 2, L.width - 30))
            if two_col else ((0, 34.0, L.width - 28),))
    for col, x0, x1 in cols:
        # centred headers (col -1) occupy space in both columns
        boxes = sorted([l[2] for l in lines if l[1] in (col, -1)], key=lambda b: b[1])
        gaps, cursor = [], L.top
        for b in boxes:
            if b[1] - cursor >= FIG_MIN_H:
                gaps.append((cursor, b[1]))
            cursor = max(cursor, b[3])
        if L.bot - cursor >= FIG_MIN_H:
            gaps.append((cursor, L.bot))

        for gi, (gy0, gy1) in enumerate(gaps):
            rect = pymupdf.Rect(x0, gy0 + 1, x1, gy1 - 1)
            if rect.height < FIG_MIN_H or rect.width < 40:
                continue
            pix = page.get_pixmap(clip=rect, dpi=FIG_DPI, colorspace=pymupdf.csGRAY)
            if blankness(pix) > 0.99:
                continue
            name = f"p{pageno:04d}_c{col}_{gi}.png"
            pix.save(os.path.join(img_dir, name))
            results.append((col, gy0, f"images/{name}"))
    return results


def blankness(pix):
    data = pix.samples
    step = max(1, len(data) // 20000)
    sample = data[::step]
    return sum(1 for v in sample if v > 235) / max(1, len(sample))


# ---------------------------------------------------------------- assembly

def build_stream(doc, L, first, last, img_dir):
    """Walk the pages and emit a flat list of items in reading order."""
    stream = []
    printed = None
    for pno in range(first, min(last, doc.page_count)):
        page = doc[pno]
        lines, two_col = page_lines(page, L)
        if not lines:
            continue
        figs = crop_figures(page, lines, two_col, pno + 1, L, img_dir) if img_dir else []

        paras = {}
        for bno, col, bbox, text, size in lines:
            if is_page_number(text, bbox, L):
                printed = text.strip()
                continue
            paras.setdefault((col, bno), []).append((bbox, text, size))

        items = []
        for (col, bno), ls in paras.items():
            ls.sort(key=lambda t: t[0][1])
            body = ls[0][1]
            for nxt in ls[1:]:
                body = glue(body, nxt[1])
            items.append((col, min(l[0][1] for l in ls), "text", body))
        for col, gy0, path in figs:
            items.append((col, gy0, "fig", path))
        items.sort(key=lambda t: (t[0], t[1]))

        stream.append({"kind": "page", "pdf_page": pno + 1, "printed": printed})
        for col, top, kind, payload in items:
            if kind == "fig":
                stream.append({"kind": "fig", "path": payload, "pdf_page": pno + 1})
                continue
            k, val = classify(payload)
            if k:
                stream.append({"kind": k, "val": val, "pdf_page": pno + 1})
        if (pno + 1) % 50 == 0:
            print(f"  ...page {pno + 1}/{doc.page_count}", flush=True)
    return stream


def merge_bodies(stream):
    """Rejoin body paragraphs the OCR chopped in half (incl. across pages)."""
    out = []
    for item in stream:
        if item["kind"] == "body" and out and out[-1]["kind"] == "body":
            prev, nxt = out[-1]["val"], item["val"]
            if prev.endswith(("-", "¬")) or (
                    not RE_ENDS_SENTENCE.search(prev) and nxt[:1].islower()):
                out[-1]["val"] = glue(prev, nxt)
                continue
        out.append(item)
    return out


def render(stream, titles):
    md = []
    pending_chapter = None
    for item in stream:
        k = item["kind"]
        if k == "page":
            md.append(f"\n<!-- pdf page {item['pdf_page']}" +
                      (f" | printed page {item['printed']}" if item["printed"] else "") +
                      " -->")
        elif k == "fig":
            md.append(f"\n![Figure, page {item['pdf_page']}]({item['path']})")
        elif k == "chapter":
            num, rest = item["val"]
            toc = titles.get(int(num), "")
            title = toc or (titlecase(rest) if rest.upper() == rest else rest)
            pending_chapter = (len(md), bool(toc))
            md.append(f"\n## Chapter {num}" + (f" — {title}" if title else ""))
        elif k == "head":
            # the chapter title is printed on the line below "Chapter N";
            # the contents page spells it better than the OCR does
            if pending_chapter is not None and len(md) - pending_chapter[0] <= 2:
                idx, had_toc = pending_chapter
                if not had_toc:
                    md[idx] += f" — {item['val']}"
                pending_chapter = None
            else:
                md.append(f"\n### {item['val']}")
        elif k == "sec":
            num, title = item["val"]
            md.append(f"\n### Sec. {num}" + (f" {title}" if title else ""))
        elif k == "caption":
            md.append(f"\n*{item['val']}*")
        else:
            md.append(f"\n{item['val']}")
        if k not in ("page", "head", "chapter"):
            pending_chapter = None
    return "\n".join(md)


def front_matter(doc):
    meta = doc.metadata or {}
    title = (meta.get("title") or "").strip()
    author = (meta.get("author") or "").strip()
    head = f"# {title}\n" if title else ""
    if author:
        head += f"\n*{author}*\n"
    head += ("\n> Converted from the scanned PDF's OCR text layer. The wording follows\n"
             "> the scan, so occasional OCR errors remain; figures are cropped from the\n"
             "> page images and HTML comments mark the page boundaries.\n")
    return head


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not args:
        print(__doc__)
        return 1
    pdf = os.path.abspath(args[0])
    root = os.path.dirname(os.path.dirname(pdf))          # .../books
    stem = os.path.splitext(os.path.basename(pdf))[0]
    out_dir = os.path.abspath(args[1]) if len(args) > 1 \
        else os.path.join(root, "processed", stem)
    img_dir = None if "--no-images" in sys.argv else os.path.join(out_dir, "images")
    os.makedirs(img_dir or out_dir, exist_ok=True)

    doc = pymupdf.open(pdf)
    L = Layout(doc)
    first = int(os.environ.get("FIRST", 0))
    last = int(os.environ.get("LAST", doc.page_count))

    stream = merge_bodies(build_stream(doc, L, first, last, img_dir))
    body = re.sub(r"\n{3,}", "\n\n", render(stream, toc_titles(doc)))

    path = os.path.join(out_dir, stem + ".md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(front_matter(doc) + body + "\n")
    print("wrote", path, os.path.getsize(path), "bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
