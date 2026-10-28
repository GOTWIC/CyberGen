"""Glyph strokes for signs (scope 5.5, decision 13.3: fonts later).

- **Latin**: an in-repo stroke font, uppercase, digits and a little punctuation, as polylines
  on a 4 by 6 grid (cap height 6, baseline 0), corners cut at 45 degrees as bent neon tubes
  are; the advance is 5.5 units, a space 3.
- **Cyrillic**: the Latin font with the letters that differ drawn apart (Б Г Д Ж И Л П Ф Ц Ш
  Э Ю Я), reached from Latin text by a fixed letter map.
- **Generated glyphs** for the scripts decision 13.3 leaves without font files (hanzi,
  kana, hangul, devanagari): each a set of strokes on a 6 by 6 cell drawn from a blake2b hash
  of (script, word, index) by a small grammar per script: hanzi from horizontals,
  verticals, falling strokes and enclosures in left-right or top-bottom halves; hangul as
  syllable blocks of an initial (corner, box, ring, roof), a vowel bar with ticks and an
  optional final; kana as two or three bent strokes; devanagari hanging strokes under a
  head bar. They read as signage in those scripts from the street; they are not words.
  Real fonts replace them when decision 13.3 vendors them.

`layout(text, script, key)` gives the strokes of a line of text in units (x from 0, y from
0 up), and its width.
"""

from __future__ import annotations

from . import styles as ST

ADV = 5.5
SPACE = 3.0
CAP = 6.0

_LATIN = {
    "A": "0,0 0,4 2,6 4,4 4,0;0,3 4,3",
    "B": "0,0 0,6 3,6 4,5 4,4 3,3 0,3;3,3 4,2 4,1 3,0 0,0",
    "C": "4,5 3,6 1,6 0,5 0,1 1,0 3,0 4,1",
    "D": "0,0 0,6 3,6 4,5 4,1 3,0 0,0",
    "E": "4,6 0,6 0,0 4,0;0,3 3,3",
    "F": "4,6 0,6 0,0;0,3 3,3",
    "G": "4,5 3,6 1,6 0,5 0,1 1,0 3,0 4,1 4,3 2,3",
    "H": "0,0 0,6;4,0 4,6;0,3 4,3",
    "I": "1,6 3,6;2,6 2,0;1,0 3,0",
    "J": "4,6 4,1 3,0 1,0 0,1",
    "K": "0,0 0,6;4,6 0,2;1,3 4,0",
    "L": "0,6 0,0 4,0",
    "M": "0,0 0,6 2,3 4,6 4,0",
    "N": "0,0 0,6 4,0 4,6",
    "O": "1,0 0,1 0,5 1,6 3,6 4,5 4,1 3,0 1,0",
    "P": "0,0 0,6 3,6 4,5 4,4 3,3 0,3",
    "Q": "1,0 0,1 0,5 1,6 3,6 4,5 4,1 3,0 1,0;2,2 4,0",
    "R": "0,0 0,6 3,6 4,5 4,4 3,3 0,3;2,3 4,0",
    "S": "4,5 3,6 1,6 0,5 0,4 1,3 3,3 4,2 4,1 3,0 1,0 0,1",
    "T": "0,6 4,6;2,6 2,0",
    "U": "0,6 0,1 1,0 3,0 4,1 4,6",
    "V": "0,6 2,0 4,6",
    "W": "0,6 1,0 2,3 3,0 4,6",
    "X": "0,6 4,0;0,0 4,6",
    "Y": "0,6 2,3 4,6;2,3 2,0",
    "Z": "0,6 4,6 0,0 4,0",
    "0": "1,0 0,1 0,5 1,6 3,6 4,5 4,1 3,0 1,0",
    "1": "1,5 2,6 2,0;1,0 3,0",
    "2": "0,5 1,6 3,6 4,5 4,4 0,0 4,0",
    "3": "0,5 1,6 3,6 4,5 4,4 3,3 1,3;3,3 4,2 4,1 3,0 1,0 0,1",
    "4": "3,0 3,6 0,2 4,2",
    "5": "4,6 0,6 0,3 3,3 4,2 4,1 3,0 1,0 0,1",
    "6": "4,5 3,6 1,6 0,5 0,1 1,0 3,0 4,1 4,2 3,3 0,3",
    "7": "0,6 4,6 1,0",
    "8": "1,3 0,4 0,5 1,6 3,6 4,5 4,4 3,3 1,3 0,2 0,1 1,0 3,0 4,1 4,2 3,3",
    "9": "0,1 1,0 3,0 4,1 4,5 3,6 1,6 0,5 0,4 1,3 4,3",
    "-": "1,3 3,3",
    ".": "1.6,0 2.4,0 2.4,0.8 1.6,0.8 1.6,0",
    "&": "4,0 1,4 1,5 2,6 3,5 3,4 0,2 0,1 1,0 2,0 4,2",
    "'": "2,6 2,4.6",
    "!": "2,6 2,2;1.6,0 2.4,0 2.4,0.8 1.6,0.8 1.6,0",
    "#": "1,0 1,6;3,0 3,6;0,2 4,2;0,4 4,4",
    "+": "2,1 2,5;0,3 4,3",
    "/": "0,0 4,6",
    ":": "1.6,4 2.4,4 2.4,4.8 1.6,4.8 1.6,4;1.6,1 2.4,1 2.4,1.8 1.6,1.8 1.6,1",
    "*": "2,1 2,5;0.5,2 3.5,4;0.5,4 3.5,2",
}
_CYRILLIC = {
    "Б": "4,6 0,6 0,0 3,0 4,1 4,2 3,3 0,3",
    "Г": "4,6 0,6 0,0",
    "Д": "-0.5,-1 -0.5,0 4.5,0 4.5,-1;0.5,0 1.5,6 3.5,6 3.5,0",
    "Ж": "0,0 2,3 0,6;4,0 2,3 4,6;2,0 2,6",
    "И": "0,6 0,0 4,6 4,0",
    "Л": "0,0 1,1 1.5,6 4,6 4,0",
    "П": "0,0 0,6 4,6 4,0",
    "Ф": "2,0 2,6;1,5 0,4 0,2 1,1 3,1 4,2 4,4 3,5 1,5",
    "Ц": "0,6 0,0 4,0 4,6;4,0 4.6,0 4.6,-1",
    "Ш": "0,6 0,0 4,0 4,6;2,0 2,6",
    "Э": "0,5 1,6 3,6 4,5 4,1 3,0 1,0 0,1;1.5,3 4,3",
    "Ю": "0,0 0,6;0,3 1.4,3;2.4,1 2.4,5 3,6 3.6,6 4.2,5 4.2,1 3.6,0 3,0 2.4,1",
    "Я": "4,0 4,6 1,6 0,5 0,4 1,3 4,3;2,3 0,0",
}
CYR_MAP = {"B": "Б", "G": "Г", "D": "Д", "J": "Ж", "I": "И", "L": "Л", "P": "П", "F": "Ф",
           "C": "Ц", "W": "Ш", "E": "Э", "U": "Ю", "R": "Я", "Z": "Ж"}


def _parse(s: str) -> list[list[tuple[float, float]]]:
    out = []
    for stroke in s.split(";"):
        out.append([tuple(float(v) for v in p.split(",")) for p in stroke.split()])
    return out


LATIN = {k: _parse(v) for k, v in _LATIN.items()}
CYRILLIC = {k: _parse(v) for k, v in _CYRILLIC.items()}


def latin_glyph(ch: str):
    return LATIN.get(ch.upper())


# ---------------------------------------------------------------------------------------
# generated glyphs
# ---------------------------------------------------------------------------------------

def _hanzi_part(key, x0: float, y0: float, x1: float, y1: float, depth: int = 0) -> list:
    """Strokes filling a box: a radical of 2 to 4 strokes, or the box split again."""
    out = []
    w, h = x1 - x0, y1 - y0
    r = ST.u(*key, "split", depth)
    if depth < 1 and w > 3.0 and r < 0.3:
        m = x0 + w * (0.38 + 0.2 * ST.u(*key, "mx"))
        return _hanzi_part((*key, "l"), x0, y0, m - 0.3, y1, depth + 1) + \
            _hanzi_part((*key, "r"), m + 0.3, y0, x1, y1, depth + 1)
    if depth < 1 and h > 3.0 and r < 0.55:
        m = y0 + h * (0.4 + 0.2 * ST.u(*key, "my"))
        return _hanzi_part((*key, "b"), x0, y0, x1, m - 0.3, depth + 1) + \
            _hanzi_part((*key, "t"), x0, m + 0.3, x1, y1, depth + 1)
    if r > 0.88:
        # an enclosure with a stroke inside
        out.append([(x0, y0), (x0, y1), (x1, y1), (x1, y0), (x0, y0)])
        out.append([(x0 + w * 0.25, (y0 + y1) / 2.0), (x1 - w * 0.25, (y0 + y1) / 2.0)])
        return out
    n = 2 + int(3 * ST.u(*key, "n", depth))
    for i in range(n):
        t = ST.u(*key, "k", depth, i)
        a, b = ST.u(*key, "a", depth, i), ST.u(*key, "b", depth, i)
        if t < 0.38:
            y = y0 + h * (0.15 + 0.7 * a)
            out.append([(x0 + w * 0.1 * b, y), (x1 - w * 0.1 * (1 - b), y)])
        elif t < 0.7:
            x = x0 + w * (0.15 + 0.7 * a)
            out.append([(x, y1 - h * 0.05), (x, y0 + h * 0.1 * b)])
        elif t < 0.85:
            out.append([(x0 + w * (0.5 + 0.3 * a), y1), (x0 + w * 0.1, y0 + h * 0.2 * b)])
        else:
            out.append([(x0 + w * (0.3 + 0.2 * a), y0 + h * (0.6 + 0.3 * b)),
                        (x1 - w * 0.1, y0 + h * 0.05)])
    return out


def _hangul(key) -> list:
    out = []
    final = ST.u(*key, "final") < 0.45
    yb = 2.4 if final else 0.0
    vowel_right = ST.u(*key, "vr") < 0.6
    ix1 = 3.4 if vowel_right else 6.0
    iy0 = yb + (0.0 if vowel_right else 2.2)
    form = ST.pick(4, *key, "init")
    x0, x1, y0, y1 = 0.2, ix1 - 0.4, iy0 + 0.2, 6.0
    if form == 0:      # corner
        out.append([(x0, y1), (x1, y1), (x1, y0)])
    elif form == 1:    # box
        out.append([(x0, y0), (x0, y1), (x1, y1), (x1, y0), (x0, y0)])
    elif form == 2:    # ring
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        rx, ry = (x1 - x0) / 2.0, (y1 - y0) / 2.0
        out.append([(cx + rx * c, cy + ry * s) for c, s in
                    ((1, 0), (0.7, 0.7), (0, 1), (-0.7, 0.7), (-1, 0), (-0.7, -0.7), (0, -1),
                     (0.7, -0.7), (1, 0))])
    else:              # roof
        out.append([(x0, y0), ((x0 + x1) / 2.0, y1), (x1, y0)])
    if vowel_right:
        out.append([(4.6, yb + 0.3), (4.6, 6.0)])
        out.append([(4.6, yb + 3.0), (5.8, yb + 3.0)] if ST.u(*key, "tick") < 0.6
                   else [(3.6, yb + 3.0), (4.6, yb + 3.0)])
    else:
        out.append([(0.2, yb + 1.6), (5.8, yb + 1.6)])
        out.append([(3.0, yb + 1.6), (3.0, yb + 2.4)])
    if final:
        out.append([(0.4, 1.9), (5.4, 1.9), (5.4, 0.1)] if ST.u(*key, "fk") < 0.5 else
                   [(0.4, 1.9), (0.4, 0.1), (5.4, 0.1)])
    return out


def _kana(key) -> list:
    out = []
    n = 2 + int(2 * ST.u(*key, "n"))
    for i in range(n):
        a, b, c = (ST.u(*key, t, i) for t in ("a", "b", "c"))
        x0, y0 = 0.5 + 3.0 * a, 4.5 + 1.5 * b
        x1, y1 = 1.0 + 4.0 * c, 0.4 + 2.5 * a
        mx, my = (x0 + x1) / 2.0 + 1.5 * (b - 0.5), (y0 + y1) / 2.0 + 1.0 * (c - 0.5)
        out.append([(x0, y0), (mx, my), (x1, y1)])
    return out


def _devanagari(key) -> list:
    out = [[(0.0, 5.6), (5.5, 5.6)]]
    out.append([(4.2, 5.6), (4.2, 0.0)])
    a, b = ST.u(*key, "a"), ST.u(*key, "b")
    out.append([(4.2, 3.0), (2.2, 4.0 + a), (0.6, 3.0), (1.4, 1.5 + b), (3.2, 1.6)])
    if ST.u(*key, "c") < 0.5:
        out.append([(1.0, 5.6), (1.6, 6.6), (3.0, 6.6)])
    return out


def generated(script: str, key) -> list:
    if script == "hangul":
        return _hangul(key)
    if script == "kana":
        return _kana(key)
    if script == "devanagari":
        return _devanagari(key)
    return _hanzi_part(key, 0.0, 0.0, 6.0, 6.0)


# ---------------------------------------------------------------------------------------
# lines of text
# ---------------------------------------------------------------------------------------

def layout(text: str, script: str = "latin", key=(), vertical: bool = False):
    """Strokes of a line of text in glyph units, and its (width, height): Latin and Cyrillic
    from the font (unknown characters left out), the generated scripts one glyph per
    character of `text` (its length sets the count). Vertical: glyphs stacked down from
    y = 0, each centered on x = 0."""
    strokes, w = [], 0.0
    glyphs = []
    if script in ("latin", "cyrillic"):
        for ch in text.upper():
            if ch == " ":
                glyphs.append(None)
                continue
            g = None
            if script == "cyrillic" and ch in CYR_MAP:
                g = CYRILLIC[CYR_MAP[ch]]
            if g is None:
                g = LATIN.get(ch)
            if g is not None:
                glyphs.append((g, 4.0))
    else:
        for i, ch in enumerate(text):
            glyphs.append(None if ch == " " else (generated(script, (*key, script, i, ch)), 6.0))
    if vertical:
        y = 0.0
        for g in glyphs:
            if g is None:
                y -= 3.0
                continue
            pts, gw = g
            y -= 6.0
            strokes += [[(x - gw / 2.0, y + yy) for x, yy in s] for s in pts]
            y -= 1.6
        return strokes, (6.0, -y - 1.6 if glyphs else 0.0)
    x = 0.0
    for g in glyphs:
        if g is None:
            x += SPACE
            continue
        pts, gw = g
        strokes += [[(x + xx, yy) for xx, yy in s] for s in pts]
        x += gw + 1.5 if gw == 4.0 else gw + 1.2
    return strokes, (max(x - 1.4, 0.0), CAP)
