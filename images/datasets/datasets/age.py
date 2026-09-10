"""Aging: the clean raster into a scan of its age, and the boxes with it"""

from datasets.draw import SynthError

AGING = {
    "clean": {},
    "scan": dict(blur=0.5, noise=3.0, speck=0.0004, tint=(244, 6, 4), skew=0.5, jpeg=85),
    "old": dict(blur=0.8, noise=5.5, speck=0.0012, tint=(232, 12, 8), skew=1.2, jpeg=68),
    "decayed": dict(
        blur=1.1,
        noise=7.5,
        speck=0.0026,
        tint=(214, 20, 14),
        skew=1.2,
        jpeg=52,
        bleed=0.16,
        edge=0.55,
    ),
}


def _age(img, profile: str, seed: int):
    import cv2
    import numpy as np

    p = AGING[profile]
    if not p:
        return (img, None)
    rng = np.random.default_rng(seed)
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    g = cv2.GaussianBlur(g, (0, 0), p["blur"])
    h, w = g.shape
    if p.get("bleed"):
        back = cv2.GaussianBlur(g[:, ::-1], (0, 0), p["blur"] * 3.0)
        sx, sy = (int(w * 0.035), int(h * 0.012))
        back = np.roll(np.roll(back, sy, axis=0), sx, axis=1)
        g = 255.0 - (255.0 - g) - p["bleed"] * (255.0 - back)
        g = np.clip(g, 0, 255)
    yy, xx = np.mgrid[0:h, 0:w]
    base, gx, gy = p["tint"]
    g = np.minimum(g, 255) / 255.0 * (base - gx * (xx / w) - gy * (yy / h))
    g += rng.normal(0, p["noise"], g.shape)
    spec = rng.random(g.shape) < p["speck"]
    g[spec] = rng.uniform(40, 120, spec.sum())
    if p.get("edge"):
        erng = np.random.default_rng(seed + 991)
        side = int(erng.integers(0, 4))
        d = int(max(6, min(h, w) * erng.uniform(0.008, 0.03)))
        k = 1.0 - p["edge"]
        if side == 0:
            g[:d, :] *= k
        elif side == 1:
            g[-d:, :] *= k
        elif side == 2:
            g[:, :d] *= k
        else:
            g[:, -d:] *= k
    g = np.clip(g, 0, 255).astype(np.uint8)
    M = None
    if p["skew"]:
        ang = np.random.default_rng(seed + 4409).uniform(-p["skew"], p["skew"])
        M = cv2.getRotationMatrix2D((w / 2, h / 2), ang, 1.0)
        g = cv2.warpAffine(g, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    ok, enc = cv2.imencode(".jpg", g, [cv2.IMWRITE_JPEG_QUALITY, p["jpeg"]])
    if not ok:
        raise SynthError("could not re-compress the page to JPEG")
    return (cv2.imdecode(enc, cv2.IMREAD_COLOR), M)


def _binding(img, seed: int):
    import numpy as np

    rng = np.random.default_rng(seed + 7)
    h, w = img.shape[:2]
    cx = w // 2 + int(rng.integers(-w // 60, w // 60))
    band = max(8, w // 40)
    xx = np.arange(w)
    prof = np.exp(-((xx - cx) ** 2) / (2 * (band / 2.2) ** 2))
    depth = np.linspace(0.62, 0.3, h)[:, None] * prof[None, :]
    out = img.astype(np.float32) * (1.0 - depth[:, :, None])
    return (np.clip(out, 0, 255).astype(np.uint8), cx)


def _xform_box(box, M):
    import numpy as np

    x0, y0, x1, y1 = box
    pts = np.array([[x0, y0, 1], [x1, y0, 1], [x1, y1, 1], [x0, y1, 1]]).T
    q = M @ pts
    return (float(q[0].min()), float(q[1].min()), float(q[0].max()), float(q[1].max()))


def _clip_box(box, w, h):
    x0, y0, x1, y1 = box
    return (max(0.0, min(x0, w)), max(0.0, min(y0, h)), max(0.0, min(x1, w)), max(0.0, min(y1, h)))


def _rot90_box(box, src_h):
    x0, y0, x1, y1 = box
    return (src_h - 1 - y1, x0, src_h - y0, x1)
