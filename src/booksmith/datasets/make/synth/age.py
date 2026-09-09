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
    # decayed: show-through from the back and a dark scan edge added to `old`.
    # Neither moves a truth box. The skew is DELIBERATELY that of `old`, skew
    # being the ONLY part of aging that does move them (through `_xform_box`);
    # at equal skew the two profiles' boxes match byte for byte, so a
    # difference in the number belongs to the paper. The old edition set 1.8
    # while the README promised "decayed does not move truth boxes" -- it moved
    # all 382.
    "decayed": dict(blur=1.1, noise=7.5, speck=0.0026, tint=(214, 20, 14),
                   skew=1.2, jpeg=52, bleed=0.16, edge=0.55),
}


def _age(img, profile: str, seed: int):
    """Age the raster. Returns (raster, rotation matrix or None).

    Aging is not decoration: measured on one page, the CLEAN page has no
    `table` box at all while the aged one grows one (0.583) -- with a competing
    `text` 0.567 on the same rectangle, the signature of the very defect
    diagnosed on a real book. Clean paper would measure a different task.
    """
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
        # Show-through: the mirrored page, blurred and weak. The plague of old
        # thin paper, and exactly the kind of "text" that is not on the page
        # while a box can still land on it. With an OFFSET: without one,
        # symmetric layout puts the mirror on its own text and show-through
        # becomes thicker ink, testing something other than its name. A book's
        # back lines up with its front neither by line nor by column.
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
        # Dark scan edge: a book shot on a flatbed has a black border. A band
        # 1-3% of the sheet wide, on one random side. Its own generator, or the
        # edge draws would shift the stream and the SKEW ANGLE of a profile
        # with an edge would differ from one without -- truth boxes diverging
        # where a match is promised.
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
        # many draws were taken above, and that count depends on `speck`. That
        # is how two profiles with the SAME skew diverged on all 382 truth
        # boxes, by up to 28 pixels, and cross-profile comparison silently
        # measured a different truth.
        ang = np.random.default_rng(seed + 4409).uniform(-p["skew"], p["skew"])
        M = cv2.getRotationMatrix2D((w / 2, h / 2), ang, 1.0)
        g = cv2.warpAffine(g, M, (w, h), flags=cv2.INTER_CUBIC,
                           borderMode=cv2.BORDER_REPLICATE)
    ok, enc = cv2.imencode(".jpg", g, [cv2.IMWRITE_JPEG_QUALITY, p["jpeg"]])
    if not ok:
        raise SynthError("could not re-compress the page to JPEG")
    return cv2.imdecode(enc, cv2.IMREAD_COLOR), M


def _binding(img, seed: int):
    """The binding shadow down the middle of a spread.

    The very shadow the cut veto once got wrong eleven times out of eleven: the
    blackness at the gutter came from the shadow while the code checked a band
    rather than a continuous rule. A synthetic spread must carry it, or the
    veto is checked on a case that does not exist in nature.
    """
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
    """A box after an affine transform: the rectangle bounding its corners.

    For a model with axis-aligned boxes that is the correct truth: a rotated
    rectangle cannot be expressed there, and the one bounding it is exactly
    what the detector is obliged to return.
    """
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
    """A box after the raster is rotated 90° clockwise.

    A point y goes to x' = src_h - 1 - y, so [y0, y1] becomes
    [src_h-1-y1, src_h-1-y0]; the RIGHT edge is half-open and so equals
    src_h - y0, not src_h - 1 - y0. The old edition lost a pixel on every box
    of a rotated page -- little, but exactly the direction the truth is obliged
    not to err in.
    """
    x0, y0, x1, y1 = box
    return (src_h - 1 - y1, x0, src_h - y0, x1)



