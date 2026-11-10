"""Finishing passes on the car renders (PIL and numpy only).

    python post.py bloom IN.jpg OUT.jpg [strength] [threshold]
    python post.py sheet DIR OUT.jpg       hero on top, front, side and back below
"""
import os
import sys

import numpy as np
from PIL import Image, ImageFilter


def bloom(src, dst, k=1.0, th=0.80):
    """Light bleeding out of what is brighter than th, as a lens would show it."""
    im = Image.open(src).convert("RGB")
    a = np.asarray(im).astype(np.float32) / 255.0
    mask = np.clip((a.max(axis=2) - th) / (1 - th), 0, 1) ** 2
    lit = Image.fromarray((np.clip(a * mask[..., None], 0, 1) * 255).astype(np.uint8))
    s = im.width / 1920.0
    out = a.copy()
    for r, w in ((5, 0.55), (18, 0.45), (55, 0.35), (140, 0.25)):
        small = r > 10
        g = lit.resize((im.width // 4, im.height // 4), Image.BILINEAR) if small else lit
        g = g.filter(ImageFilter.GaussianBlur(r * s / (4 if small else 1)))
        g = np.asarray(g.resize(im.size, Image.BILINEAR)).astype(np.float32) / 255.0
        out = 1 - (1 - out) * (1 - np.clip(g * w * k * 2.0, 0, 1))
    Image.fromarray((np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8)).save(dst, quality=94)


def cut(im, w, h, cy=0.5):
    """The largest centered crop of im with the aspect w : h, scaled to w x h."""
    W, H = im.size
    if W * h > H * w:
        cw, ch = int(H * w / h), H
    else:
        cw, ch = W, int(W * h / w)
    x0 = (W - cw) // 2
    y0 = min(max(int(H * cy - ch / 2), 0), H - ch)
    return im.crop((x0, y0, x0 + cw, y0 + ch)).resize((w, h), Image.LANCZOS)


def sheet(d, dst):
    def load(n):
        return Image.open(os.path.join(d, "car_%s.jpg" % n)).convert("RGB")
    W, top, row, gap = 3840, 1536, 620, 4
    out = Image.new("RGB", (W, top + gap + row), (14, 14, 16))
    out.paste(cut(load("hero"), W, top, 0.52), (0, 0))
    x = 0
    for n, w in (("front", 800 - gap), ("side", 2240 - gap), ("back", 800)):
        out.paste(cut(load(n), w, row, 0.53), (x, top + gap))
        x += w + gap
    out.save(dst, quality=93)


if __name__ == "__main__":
    if sys.argv[1] == "bloom":
        bloom(sys.argv[2], sys.argv[3], *[float(v) for v in sys.argv[4:6]])
    else:
        sheet(sys.argv[2], sys.argv[3])
