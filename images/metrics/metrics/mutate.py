def map_boxes(M, fn):
    return {i: {**p, "blocks": [{**b, "box": list(fn(b["box"]))} for b in p["blocks"]]} for i, p in M.items()}


def shift(M, dx, dy):
    return map_boxes(M, lambda b: (b[0] + dx, b[1] + dy, b[2] + dx, b[3] + dy))


def shift_rel(M, frac):

    def g(b):
        d = frac * max(4.0, min(b[2] - b[0], b[3] - b[1]))
        return (b[0] + d, b[1] + d, b[2] + d, b[3] + d)

    return map_boxes(M, g)


def grow(M, f):

    def g(b):
        cx, cy = ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)
        w, h = ((b[2] - b[0]) * f / 2, (b[3] - b[1]) * f / 2)
        return (cx - w, cy - h, cx + w, cy + h)

    return map_boxes(M, g)


def only(M, keep):
    return {i: {**p, "blocks": [b for b in p["blocks"] if keep(b)]} for i, p in M.items()}


def relabel(M, fn):
    return {i: {**p, "blocks": [{**b, "label": fn(b["label"])} for b in p["blocks"]]} for i, p in M.items()}


def duplicate(M):
    return {i: {**p, "blocks": [c for b in p["blocks"] for c in (b, dict(b))]} for i, p in M.items()}


def shuffle_pages(M):
    keys = sorted(M)
    return {k: {**M[keys[(n + 1) % len(keys)]], "index": k} for n, k in enumerate(keys)}
