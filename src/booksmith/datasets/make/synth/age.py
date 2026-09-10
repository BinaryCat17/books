"""Aging: the clean raster into a scan of its age, and the boxes with it.

Blur, noise, specks, tint, skew and jpeg by profile; the binding shadow on
spreads; and the three box transforms (affine, clip, rotate by ninety)
that carry the truth through what was done to the page, so that truth
never has to be re-measured on an aged image.
"""
from booksmith.datasets.make.synth.draw import SynthError

# --------------------------------------------------------------------- aging
# Profiles are NAMED sets, not scattered knobs: their parameters go into the
# snapshot whole, so naming the profile is enough to repeat a run.
AGING = {
    "clean": {},
    "scan": dict(blur=0.5, noise=3.0, speck=0.0004, tint=(244, 6, 4),
                 skew=0.5, jpeg=85),
    "old": dict(blur=0.8, noise=5.5, speck=0.0012, tint=(232, 12, 8),
                skew=1.2, jpeg=68),
    # decayed: show-through from the back and a dark scan edge over `old`.
    # Neither moves a truth box, and the skew is DELIBERATELY `old`'s -- skew is
    # the only part of aging that does move them -- so at equal skew the two
    # profiles' boxes match byte for byte and a difference belongs to the paper.
    "decayed": dict(blur=1.1, noise=7.5, speck=0.0026, tint=(214, 20, 14),
                   skew=1.2, jpeg=52, bleed=0.16, edge=0.55),
}


def _age(img, profile: str, seed: int):
    """Age the raster; returns (raster, rotation matrix or None). Aging is not
    decoration: on one page the clean raster yields no `table` box at all while
    the aged one does, so clean paper would measure a different task."""
    import cv2
    import numpy as np

    p = AGING[profile]
    if not p:
        return img, None
    rng = np.random.default_rng(seed)
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    g = cv2.GaussianBlur(g, (0, 0), p["blur"])          # ink spread
    h, w = g.shape
    if p.get("bleed"):
        # Show-through: the mirrored page, blurred and weak -- the kind of
        # "text" that is not on the page while a box can still land on it. WITH
        # AN OFFSET, or a symmetric layout puts the mirror on its own text and
        # show-through becomes thicker ink instead.
        back = cv2.GaussianBlur(g[:, ::-1], (0, 0), p["blur"] * 3.0)
        sx, sy = int(w * 0.035), int(h * 0.012)
        back = np.roll(np.roll(back, sy, axis=0), sx, axis=1)
        g = 255.0 - (255.0 - g) - p["bleed"] * (255.0 - back)
        g = np.clip(g, 0, 255)
    yy, xx = np.mgrid[0:h, 0:w]
    base, gx, gy = p["tint"]
    g = np.minimum(g, 255) / 255.0 * (base - gx * (xx / w) - gy * (yy / h))
    g += rng.normal(0, p["noise"], g.shape)             # paper grain
    spec = rng.random(g.shape) < p["speck"]             # specks
    g[spec] = rng.uniform(40, 120, spec.sum())
    if p.get("edge"):
        # Dark scan edge: a band 1-3% of the sheet wide on one random side. Its
        # OWN generator, or these draws shift the stream and with it the skew
        # angle, so a profile with an edge would move truth boxes and one
        # without would not.
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
        # Its OWN generator: from the shared one the angle would depend on how
        # many draws `speck` took above, and two profiles with the same skew
        # would diverge on every truth box.
        ang = np.random.default_rng(seed + 4409).uniform(-p["skew"], p["skew"])
        M = cv2.getRotationMatrix2D((w / 2, h / 2), ang, 1.0)
        g = cv2.warpAffine(g, M, (w, h), flags=cv2.INTER_CUBIC,
                           borderMode=cv2.BORDER_REPLICATE)
    ok, enc = cv2.imencode(".jpg", g, [cv2.IMWRITE_JPEG_QUALITY, p["jpeg"]])
    if not ok:
        raise SynthError("could not re-compress the page to JPEG")
    return cv2.imdecode(enc, cv2.IMREAD_COLOR), M


def _binding(img, seed: int):
    """The binding shadow down the middle of a spread. A synthetic spread must
    carry it, or the spread-cut veto is checked on a case that does not exist in
    nature."""
    import numpy as np

    rng = np.random.default_rng(seed + 7)
    h, w = img.shape[:2]
    cx = w // 2 + int(rng.integers(-w // 60, w // 60))
    band = max(8, w // 40)
    xx = np.arange(w)
    prof = np.exp(-((xx - cx) ** 2) / (2 * (band / 2.2) ** 2))
    # Denser at the top: on spread scans the head of the gutter is blackest.
    depth = np.linspace(0.62, 0.30, h)[:, None] * prof[None, :]
    out = img.astype(np.float32) * (1.0 - depth[:, :, None])
    return np.clip(out, 0, 255).astype(np.uint8), cx


def _xform_box(box, M):
    """A box after an affine transform: the rectangle bounding its corners. For
    a model with axis-aligned boxes that IS the correct truth -- a rotated
    rectangle cannot be expressed there, and the bounding one is what it owes."""
    import numpy as np
    x0, y0, x1, y1 = box
    pts = np.array([[x0, y0, 1], [x1, y0, 1], [x1, y1, 1], [x0, y1, 1]]).T
    q = M @ pts
    return (float(q[0].min()), float(q[1].min()),
            float(q[0].max()), float(q[1].max()))


def _clip_box(box, w, h):
    """A box inside the raster. Skew pushes edges off the sheet, and unclipped
    the truth would partly lie outside the page -- where the model cannot put a
    box by construction, so the miss would be undeserved."""
    x0, y0, x1, y1 = box
    return (max(0.0, min(x0, w)), max(0.0, min(y0, h)),
            max(0.0, min(x1, w)), max(0.0, min(y1, h)))


def _rot90_box(box, src_h):
    """A box after the raster is rotated 90° clockwise. A point y goes to
    x' = src_h - 1 - y, and the RIGHT edge is half-open, so it equals src_h - y0
    and not src_h - 1 - y0."""
    x0, y0, x1, y1 = box
    return (src_h - 1 - y1, x0, src_h - y0, x1)



