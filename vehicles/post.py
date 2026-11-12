"""Finishing passes on the vehicle renders (PIL and numpy only).

    python post.py bloom IN.jpg OUT.jpg [strength] [threshold]
    python post.py gif OUT.gif FRAME.jpg ...        frames in turn, looping (the turntable)
    python post.py compose OUT.jpg [--bloom K TH] [--gap N] [--inset E.jpg tr] ...
                           --row A.jpg B.jpg --row C.jpg ...
                                           tiles as rendered, row under row (carkit's
                                           --sheet and --preview call this)
"""
import sys

import numpy as np
from PIL import Image, ImageFilter


def bloomed(im, k=1.0, th=0.80):
    """Light bleeding out of what is brighter than th, as a lens would show it."""
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
    return Image.fromarray((np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8))


def bloom(src, dst, k=1.0, th=0.80):
    bloomed(Image.open(src).convert("RGB"), k, th).save(dst, quality=94)


def compose(dst, rows, gap=4, glow=None, inset=None):
    """Rows of tiles at their own sizes, left to right, row under row, gap between.
    inset: (file, corner) lays a small tile into a corner ("tl", "tr", "bl", "br") of the
    first tile, a gap round its inner sides; a list of such pairs lays several."""
    ims = [[Image.open(p).convert("RGB") for p in row] for row in rows]
    if glow:
        ims = [[bloomed(im, *glow) for im in row] for row in ims]
    for one in ([inset] if inset and isinstance(inset[0], str) else inset or []):
        small = Image.open(one[0]).convert("RGB")
        if glow:
            small = bloomed(small, *glow)
        big = ims[0][0]
        inset = one
        x = 0 if inset[1][1] == "l" else big.width - small.width
        y = 0 if inset[1][0] == "t" else big.height - small.height
        big.paste((14, 14, 16), (max(x - gap, 0), max(y - gap, 0),
                                 min(x + small.width + gap, big.width),
                                 min(y + small.height + gap, big.height)))
        big.paste(small, (x, y))
    W = max(sum(im.width for im in row) + gap * (len(row) - 1) for row in ims)
    H = sum(max(im.height for im in row) for row in ims) + gap * (len(ims) - 1)
    out = Image.new("RGB", (W, H), (14, 14, 16))
    y = 0
    for row in ims:
        x = 0
        for im in row:
            out.paste(im, (x, y))
            x += im.width + gap
        y += max(im.height for im in row) + gap
    out.save(dst, quality=93)


if __name__ == "__main__":
    if sys.argv[1] == "bloom":
        bloom(sys.argv[2], sys.argv[3], *[float(v) for v in sys.argv[4:6]])
    elif sys.argv[1] == "compose":
        a, rows, gap, glow, inset = sys.argv[3:], [], 4, None, []
        while a:
            if a[0] == "--row":
                rows.append([])
            elif a[0] == "--gap":
                gap = int(a.pop(1))
            elif a[0] == "--bloom":
                glow = (float(a.pop(1)), float(a.pop(1)))
            elif a[0] == "--inset":
                inset.append((a.pop(1), a.pop(1)))
            else:
                rows[-1].append(a[0])
            a.pop(0)
        compose(sys.argv[2], rows, gap, glow, inset)
    elif sys.argv[1] == "gif":
        frames = [Image.open(f).convert("RGB") for f in sys.argv[3:]]
        frames[0].save(sys.argv[2], save_all=True, append_images=frames[1:], duration=110,
                       loop=0)
    else:
        sys.exit(__doc__)
