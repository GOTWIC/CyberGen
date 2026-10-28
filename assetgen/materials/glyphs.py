"""Glyphs for signage without font files (decision 13.3 defers fonts to AG8): an in-repo
stroke font and stroke-built scripts, all plain data and arithmetic.

- **Latin** (A to Z, 0 to 9, punctuation) and **Cyrillic** capitals as polylines on a 4 x 6
  grid (x right, y up, baseline 0): a technical stroke face that reads as signage lettering.
- **Katakana** (the 45 basic signs as strokes) and **Hangul** (14 consonants and the basic
  vowels as strokes, composed into syllable blocks) on a 5 x 6 box.
- **Hanzi-like** and **Devanagari-like** signs: Hanzi from a dozen stroke components
  (box, sun, tree, person, water, earth, roof, grass, ...) composed left-right, top-bottom
  or alone; Devanagari from hanging letter shapes under a head line. Both drawn from a hash
  of the syllable they stand for, so the same name always reads the same, but they are
  decorative: these are not words of those languages.

`layout(text, script)` turns a name into strokes: Latin text as is; other scripts by a
syllable transliteration of the Latin (each syllable one sign, or one block in Hangul).
Coordinates in the result are in glyph units (cap height 6); `draw` rasterizes them.
"""

from __future__ import annotations

import hashlib

# --- Latin and Cyrillic ------------------------------------------------------------------------

_O = "1,0 0,1 0,5 1,6 3,6 4,5 4,1 3,0 1,0"
_P = "0,0 0,6 3,6 4,5 4,4 3,3 0,3"
_DOT0 = "1.7,0 2.3,0 2.3,0.5 1.7,0.5 1.7,0"
LATIN = {
    "A": ["0,0 2,6 4,0", "0.8,2.4 3.2,2.4"],
    "B": ["0,0 0,6 3,6 4,5 4,4 3,3 0,3", "3,3 4,2 4,1 3,0 0,0"],
    "C": ["4,5 3,6 1,6 0,5 0,1 1,0 3,0 4,1"],
    "D": ["0,0 0,6 2.5,6 4,4.5 4,1.5 2.5,0 0,0"],
    "E": ["4,6 0,6 0,0 4,0", "0,3 3,3"],
    "F": ["4,6 0,6 0,0", "0,3 3,3"],
    "G": ["4,5 3,6 1,6 0,5 0,1 1,0 3,0 4,1 4,3 2,3"],
    "H": ["0,0 0,6", "4,0 4,6", "0,3 4,3"],
    "I": ["2,0 2,6", "1,6 3,6", "1,0 3,0"],
    "J": ["4,6 4,1 3,0 1,0 0,1"],
    "K": ["0,0 0,6", "4,6 0,2", "1.4,3.4 4,0"],
    "L": ["0,6 0,0 4,0"],
    "M": ["0,0 0,6 2,3 4,6 4,0"],
    "N": ["0,0 0,6 4,0 4,6"],
    "O": [_O],
    "P": [_P],
    "Q": [_O, "2.5,1.5 4,-0.5"],
    "R": [_P, "2,3 4,0"],
    "S": ["4,5 3,6 1,6 0,5 0,4 1,3 3,3 4,2 4,1 3,0 1,0 0,1"],
    "T": ["0,6 4,6", "2,6 2,0"],
    "U": ["0,6 0,1 1,0 3,0 4,1 4,6"],
    "V": ["0,6 2,0 4,6"],
    "W": ["0,6 1,0 2,4 3,0 4,6"],
    "X": ["0,0 4,6", "0,6 4,0"],
    "Y": ["0,6 2,3 4,6", "2,3 2,0"],
    "Z": ["0,6 4,6 0,0 4,0"],
    "0": [_O, "0.6,1 3.4,5"],
    "1": ["1,5 2,6 2,0", "1,0 3,0"],
    "2": ["0,5 1,6 3,6 4,5 4,4 0,0 4,0"],
    "3": ["0,5 1,6 3,6 4,5 4,4 3,3 1.5,3", "3,3 4,2 4,1 3,0 1,0 0,1"],
    "4": ["3,0 3,6 0,2 4,2"],
    "5": ["4,6 0,6 0,3 3,3 4,2 4,1 3,0 0,0"],
    "6": ["4,5 3,6 1,6 0,5 0,1 1,0 3,0 4,1 4,2 3,3 0,3"],
    "7": ["0,6 4,6 1.5,0"],
    "8": ["1,3 0,4 0,5 1,6 3,6 4,5 4,4 3,3 1,3 0,2 0,1 1,0 3,0 4,1 4,2 3,3"],
    "9": ["4,3 1,3 0,4 0,5 1,6 3,6 4,5 4,1 3,0 1,0 0,1"],
    "-": ["0.5,3 3.5,3"],
    ".": [_DOT0],
    ",": ["2.2,0.6 2.2,0 1.6,-0.8"],
    "'": ["2,6 2,4.8"],
    "&": ["4,0 1,4 1,5 2,6 3,5 3,4 0,2 0,1 1,0 2,0 4,2"],
    "!": ["2,6 2,1.6", _DOT0],
    "?": ["0,5 1,6 3,6 4,5 4,4 2,2.5 2,1.6", _DOT0],
    "/": ["0,0 4,6"],
    ":": [_DOT0, "1.7,3.5 2.3,3.5 2.3,4 1.7,4 1.7,3.5"],
    "+": ["2,1 2,5", "0,3 4,3"],
    "#": ["1.3,0 1.3,6", "2.7,0 2.7,6", "0,2 4,2", "0,4 4,4"],
    "$": ["4,5 3,6 1,6 0,5 0,4 1,3 3,3 4,2 4,1 3,0 1,0 0,1", "2,-0.6 2,6.6"],
    "%": ["0,0 4,6", "0,6 1,6 1,5 0,5 0,6", "3,1 4,1 4,0 3,0 3,1"],
    "@": ["3,2 3,4 1.5,4 1.5,2 3,2 4,2.5 4,5 3,6 1,6 0,5 0,1 1,0 3.5,0"],
}
CYRILLIC = {
    "Б": ["4,6 0,6 0,0 3,0 4,1 4,2 3,3 0,3"],
    "Г": ["4,6 0,6 0,0"],
    "Д": ["-0.3,-1 -0.3,0 4.3,0 4.3,-1", "0.3,0 1,6 3.6,6 3.6,0"],
    "Ж": ["2,0 2,6", "0,6 2,3 4,6", "0,0 2,3 4,0"],
    "З": ["0,5 1,6 3,6 4,5 4,4 3,3 1.5,3", "3,3 4,2 4,1 3,0 1,0 0,1"],
    "И": ["0,6 0,0 4,6 4,0"],
    "Л": ["0,0 1.5,6 4,6 4,0"],
    "П": ["0,0 0,6 4,6 4,0"],
    "У": ["0,6 2,2.5", "4,6 1,0 0,0"],
    "Ф": ["2,0 2,6", "1,1.5 0,2.5 0,4 1,5 3,5 4,4 4,2.5 3,1.5 1,1.5"],
    "Ц": ["0,6 0,0 4,0 4,6", "4,0 4.5,-1"],
    "Ч": ["0,6 0,4 1,3 4,3", "4,6 4,0"],
    "Ш": ["0,6 0,0 4,0 4,6", "2,0 2,6"],
    "Ы": ["0,6 0,0 2,0 3,1 3,2 2,3 0,3", "4,0 4,6"],
    "Э": ["0,5 1,6 3,6 4,5 4,1 3,0 1,0 0,1", "1.5,3 4,3"],
    "Ю": ["0,0 0,6", "0,3 1.5,3", "2.5,0 1.5,1 1.5,5 2.5,6 3.2,6 4,5 4,1 3.2,0 2.5,0"],
    "Я": ["4,0 4,6 1,6 0,5 0,4 1,3 4,3", "2.5,3 0,0"],
}
# Latin to Cyrillic capitals (letters that look alike keep the Latin strokes)
TO_CYR = [("SHCH", "Ш"), ("SH", "Ш"), ("CH", "Ч"), ("ZH", "Ж"), ("YA", "Я"), ("YU", "Ю"),
          ("KH", "X"), ("TS", "Ц"), ("A", "A"), ("B", "Б"), ("V", "B"), ("W", "B"),
          ("G", "Г"), ("D", "Д"), ("E", "E"), ("Z", "З"), ("I", "И"), ("J", "Ж"),
          ("K", "K"), ("L", "Л"), ("M", "M"), ("N", "H"), ("O", "O"), ("P", "П"),
          ("R", "P"), ("S", "C"), ("T", "T"), ("U", "У"), ("F", "Ф"), ("H", "X"),
          ("C", "Ц"), ("Y", "Ы"), ("X", "KC"), ("Q", "K")]

# --- katakana (5 x 6 box) --------------------------------------------------------------------

KANA = {
    "a": ["0,5.5 5,5.5 4,4 3,3", "2.5,4.2 2.5,2.5 1,0.5"],
    "i": ["4.5,5.8 0.5,2.5", "3,4 3,0"],
    "u": ["2.5,6 2.5,5", "0.5,3.5 0.5,5 4.5,5 4.5,3.5 2.5,0.5"],
    "e": ["1,5 4,5", "2.5,5 2.5,0.8", "0,0.8 5,0.8"],
    "o": ["0,4 5,4", "3.5,6 3.5,0 2.8,0.5", "3.5,4 0.5,0.8"],
    "ka": ["0.5,4.5 4.5,4.5 4.5,0.5 3.5,0.8", "2.5,6 2.2,2.5 0.5,0.3"],
    "ki": ["0.5,4.5 4.5,4.8", "0.2,2.5 4.8,2.8", "2.2,6 2.8,0"],
    "ku": ["2,6 0.3,3.3", "1.4,4.8 4.6,4.8 4.4,3.3 1.5,0"],
    "ke": ["1.5,6 0,3.5", "0.8,4.6 5,4.6", "3.2,4.6 3,2.5 1.5,0"],
    "ko": ["0.5,5 4.5,5 4.5,0.8 0.5,0.8"],
    "sa": ["0,4.2 5,4.2", "1.5,5.8 1.5,2.8", "3.5,5.8 3.5,3 2,0.2"],
    "shi": ["0.8,5.3 1.8,4.8", "0.4,3.8 1.4,3.3", "0.6,0.4 4.8,4.6"],
    "su": ["0.8,5 4.2,5 2.8,2.5 0.5,0.2", "2.8,2.5 4.6,0.5"],
    "se": ["0.2,3.8 5,4.4 3.6,3.2", "1.6,6 1.6,1 2.4,0.4 4.5,0.4"],
    "so": ["0.8,5 1.8,3.8", "4.6,5.2 1.2,0.2"],
    "ta": ["2,6 0.3,3.3", "1.4,4.8 4.6,4.8 4.4,3.3 1.5,0", "1.5,3.4 3.5,2.2"],
    "chi": ["4.2,5.8 0.8,5", "0,3.4 5,3.4", "2.6,5.2 2.6,2.8 1.2,0.2"],
    "tsu": ["0.4,5 1.2,3.8", "2.2,5.4 2.8,4.2", "4.8,5.2 1.4,0.2"],
    "te": ["1,5.6 4,5.6", "0,3.8 5,3.8", "2.5,3.8 2.4,2.2 1.2,0.4"],
    "to": ["1.8,6 1.8,0", "1.8,3.8 4,2.8"],
    "na": ["0,4 5,4", "3,6 3,2.5 1.5,0.2"],
    "ni": ["1,4.8 4,4.8", "0,1 5,1"],
    "nu": ["0.6,5 4.4,5 2.6,1.2 0.6,0.2", "1.6,2.8 4.4,0.6"],
    "ne": ["2.5,6 2.5,5", "0.5,5 4.5,5 0.5,1.5", "2.5,3 2.5,0", "3.2,2.5 4.6,1.2"],
    "no": ["4.2,5.8 0.6,0.3"],
    "ha": ["1.8,4.4 0.2,1.2", "3.2,4.4 4.8,1"],
    "hi": ["1,5.8 1,0.8 4.6,0.8", "1,3.4 4,4.2"],
    "fu": ["0.5,5 4.6,5 3.8,2.6 1.2,0.2"],
    "he": ["0,2.4 1.6,4.2 4.8,1.2"],
    "ho": ["0.2,4.2 4.8,4.2", "2.5,6 2.5,0 2,0.3", "1.3,2.8 0.3,1.2", "3.7,2.8 4.7,1.2"],
    "ma": ["0.4,5 4.6,5 2.4,2.2", "1.6,3 3.4,0.6"],
    "mi": ["1,5.4 4,4.8", "1.2,3.4 3.8,2.8", "0.8,1.2 4.4,0.4"],
    "mu": ["2.6,6 0.4,0.8 4.2,1.2", "3,2.8 4.4,0.2"],
    "me": ["4,5.6 0.6,0.2", "1.2,3.8 4.2,1"],
    "mo": ["0.8,5.2 4.2,5.2", "0,3.2 5,3.2", "2.3,5.2 2.3,0.8 3,0.3 4.6,0.3"],
    "ya": ["0,3.8 4.8,4.6 3.6,3.2", "1.6,6 2.6,0.2"],
    "yu": ["1,4.2 3.8,4.2 3.8,0.8", "0,0.8 5,0.8"],
    "yo": ["0.6,5.2 4.4,5.2 4.4,0.6 0.6,0.6", "0.8,2.9 4.4,2.9"],
    "ra": ["1,5.6 4,5.6", "0.5,3.8 4.6,3.8 3.6,1.6 1.4,0.2"],
    "ri": ["1,5 1,2", "4,5.6 4,2.6 2.2,0.2"],
    "ru": ["1.4,5.6 1.4,2.6 0.2,0.4", "3,5.8 3,0.4 4.8,1.8"],
    "re": ["1,5.8 1,0.6 4.6,2.6"],
    "ro": ["0.6,5 4.4,5 4.4,0.6 0.6,0.6 0.6,5"],
    "wa": ["0.6,3.8 0.6,5 4.4,5 4.2,3 2,0.2"],
    "n": ["0.6,5.2 1.6,4.4", "0.6,0.4 4.8,4.6"],
}
_KANA_C = {"b": "h", "p": "h", "v": "h", "d": "t", "g": "k", "z": "s", "j": "s", "c": "k",
           "q": "k", "x": "k", "l": "r", "f": "h"}

# --- Hangul (jamo in a unit box, composed into blocks) --------------------------------------

_CIRCLE = "0.5,1 0.15,0.85 0,0.5 0.15,0.15 0.5,0 0.85,0.15 1,0.5 0.85,0.85 0.5,1"
JAMO_C = {
    "g": ["0,1 1,1 1,0"], "n": ["0,1 0,0 1,0"], "d": ["1,1 0,1 0,0 1,0"],
    "r": ["0,1 1,1 1,0.5 0,0.5 0,0 1,0"], "m": ["0,0 0,1 1,1 1,0 0,0"],
    "b": ["0,1 0,0 1,0 1,1", "0,0.5 1,0.5"], "s": ["0.5,1 0,0", "0.5,0.6 1,0"],
    "": [_CIRCLE], "j": ["0,1 1,1", "0.5,1 0,0", "0.5,0.6 1,0"],
    "h": ["0.3,1 0.7,1", "0,0.82 1,0.82", "0.5,0.62 0.2,0.5 0.2,0.12 0.5,0 0.8,0.12 0.8,0.5 "
          "0.5,0.62"],
    "k": ["0,1 1,1 1,0", "0,0.5 1,0.5"], "t": ["1,1 0,1 0,0 1,0", "0,0.5 1,0.5"],
    "p": ["0,1 1,1", "0,0 1,0", "0.3,1 0.3,0", "0.7,1 0.7,0"],
    "ch": ["0.3,1.15 0.7,1.15", "0,1 1,1", "0.5,1 0,0", "0.5,0.6 1,0"],
}
JAMO_V = {   # (strokes, vertical: vowel stands right of the initial)
    "a": (["0.4,1 0.4,0", "0.4,0.5 0.9,0.5"], True),
    "eo": (["0.6,1 0.6,0", "0.1,0.5 0.6,0.5"], True),
    "i": (["0.5,1 0.5,0"], True),
    "ya": (["0.4,1 0.4,0", "0.4,0.65 0.9,0.65", "0.4,0.35 0.9,0.35"], True),
    "e": (["0.3,1 0.3,0", "0.7,1 0.7,0", "0,0.5 0.3,0.5"], True),
    "o": (["0,0.25 1,0.25", "0.5,0.25 0.5,0.75"], False),
    "u": (["0,0.75 1,0.75", "0.5,0.75 0.5,0.2"], False),
    "eu": (["0,0.5 1,0.5"], False),
    "yo": (["0,0.25 1,0.25", "0.35,0.25 0.35,0.75", "0.65,0.25 0.65,0.75"], False),
}
_HAN_C = {"g": "g", "k": "k", "n": "n", "d": "d", "t": "t", "r": "r", "l": "r", "m": "m",
          "b": "b", "p": "p", "v": "b", "f": "p", "s": "s", "z": "j", "j": "j", "c": "ch",
          "h": "h", "x": "k", "q": "k", "w": "", "y": ""}
_HAN_V = {"a": "a", "e": "e", "i": "i", "o": "o", "u": "u", "y": "eu"}

# --- Hanzi-like components (unit box) ---------------------------------------------------------

COMPONENTS = {
    "kou": ["0.1,0.1 0.1,0.9 0.9,0.9 0.9,0.1 0.1,0.1"],
    "ri": ["0.2,0 0.2,1 0.8,1 0.8,0 0.2,0", "0.2,0.5 0.8,0.5"],
    "mu": ["0,0.7 1,0.7", "0.5,1 0.5,0", "0.5,0.7 0.05,0.15", "0.5,0.7 0.95,0.15"],
    "ren": ["0.55,1 0.5,0.6 0,0", "0.5,0.6 1,0"],
    "shui": ["0.2,0.95 0.4,0.8", "0.1,0.6 0.35,0.5", "0.05,0 0.4,0.35"],
    "tu": ["0.15,0.65 0.85,0.65", "0.5,1 0.5,0.05", "0,0.05 1,0.05"],
    "wang": ["0.1,0.95 0.9,0.95", "0.15,0.5 0.85,0.5", "0.05,0.05 0.95,0.05",
             "0.5,0.95 0.5,0.05"],
    "shi": ["0,0.5 1,0.5", "0.5,1 0.5,0"],
    "shan": ["0.5,0.95 0.5,0.05", "0.1,0.6 0.1,0.05 0.9,0.05 0.9,0.6"],
    "da": ["0,0.65 1,0.65", "0.5,1 0.5,0.65 0,0", "0.5,0.65 1,0"],
    "mian": ["0.5,1 0.5,0.85", "0.05,0.6 0.05,0.85 0.95,0.85 0.95,0.6"],
    "cao": ["0,0.75 1,0.75", "0.3,0.95 0.3,0.55", "0.7,0.95 0.7,0.55"],
    "xin": ["0.1,0.5 0.05,0.2", "0.3,0.7 0.3,0.05 0.9,0.05 0.95,0.3", "0.5,0.7 0.6,0.5",
            "0.85,0.7 0.95,0.5"],
    "men": ["0.1,0 0.1,0.95", "0.1,0.95 0.4,0.95", "0.6,0.95 0.9,0.95 0.9,0.05 0.75,0.1"],
    "ren2": ["0.6,1 0.05,0.45", "0.35,0.7 0.35,0"],
    "dao": ["0.1,0.85 0.9,0.85 0.85,0.1 0.7,0.15", "0.5,0.85 0.45,0.4 0.05,0"],
    "yue": ["0.15,0 0.2,0.95 0.85,0.95 0.85,0.05 0.7,0.1", "0.2,0.65 0.85,0.65",
            "0.2,0.35 0.85,0.35"],
}
SIDE = ("shui", "ren2", "tu", "wang", "kou", "ri", "mu", "xin")
TOP = ("cao", "mian", "shi", "da", "ren")
WHOLE = ("kou", "ri", "mu", "da", "shan", "tu", "wang", "men", "dao", "yue", "shi")

# --- Devanagari-like letters (hang from a head line at y 1; unit box 0..1) ------------------

DEVA = [
    ["0.7,1 0.7,0", "0.7,0.6 0.2,0.6 0.1,0.35 0.3,0.2 0.7,0.3"],                 # ka-ish
    ["0.6,1 0.6,0", "0.1,1 0.1,0.55 0.6,0.55"],                                    # na
    ["0.7,1 0.7,0", "0.1,1 0.1,0.5 0.4,0.4 0.7,0.5"],                              # ma
    ["0.3,1 0.3,0.6 0.7,0.4 0.3,0.1"],                                             # ra
    ["0.75,1 0.75,0", "0.2,1 0.2,0.7 0.5,0.55 0.75,0.6", "0.2,0.7 0.1,0.35 0.4,0.2"],
    ["0.7,1 0.7,0", "0.2,0.6 0.4,0.75 0.7,0.6"],                                   # ta
    ["0.7,1 0.7,0", "0.15,0.75 0.45,0.75 0.3,0.45 0.7,0.45"],                      # la
    ["0.7,1 0.7,0", "0.3,0.75 0.1,0.5 0.3,0.25 0.7,0.4"],                          # va
    ["0.7,1 0.7,0", "0.15,1 0.15,0.3"],                                            # ga
    ["0.7,1 0.7,0", "0.15,1 0.15,0.55 0.4,0.4 0.7,0.45"],                          # pa
    ["0.5,1 0.5,0.7 0.2,0.5 0.5,0.3 0.8,0.5 0.5,0.7"],                             # ha-ish
]


def _parse(strokes, sx=1.0, sy=1.0, ox=0.0, oy=0.0):
    out = []
    for s in strokes:
        pts = []
        for tok in s.split():
            x, y = tok.split(",")
            pts.append((ox + float(x) * sx, oy + float(y) * sy))
        out.append(pts)
    return out


def _h(*parts) -> int:
    return int.from_bytes(hashlib.blake2b("|".join(parts).encode(), digest_size=4).digest(),
                          "little")


def syllables(text: str) -> list[str]:
    """Latin text to rough syllables (consonants then a vowel; a final consonant run kept)."""
    out, cur = [], ""
    t = "".join(ch for ch in text.lower() if ch.isalpha() or ch == " ")
    for ch in t:
        if ch == " ":
            if cur:
                out.append(cur)
            out.append(" ")
            cur = ""
            continue
        cur += ch
        if ch in "aeiouy":
            out.append(cur)
            cur = ""
    if cur:
        out.append(cur)
    return out


# --- layout per script -----------------------------------------------------------------------

ADV = {"latin": 5.2, "cyrillic": 5.2, "kana": 6.6, "hangul": 7.0, "hanzi": 7.0,
       "devanagari": 4.6}


def _latin(text: str, cyr: bool = False):
    s = text.upper()
    if cyr:
        out, i = [], 0
        while i < len(s):
            for a, b in TO_CYR:
                if s.startswith(a, i):
                    out.extend(list(b))
                    i += len(a)
                    break
            else:
                out.append(s[i])
                i += 1
        s = "".join(out)
    strokes, x = [], 0.0
    for ch in s:
        if ch == " ":
            x += 3.2
            continue
        g = CYRILLIC.get(ch) or LATIN.get(ch)
        if g is None:
            continue
        strokes += _parse(g, ox=x)
        x += 5.2
    return strokes, max(x - 1.2, 0.0)


def _kana(text: str):
    strokes, x = [], 0.0
    for syl in syllables(text):
        if syl == " ":
            x += 3.0
            continue
        if not syl[-1] in "aeiouy":
            key = "n"
        else:
            c = syl[:-1][-1:] if len(syl) > 1 else ""
            v = syl[-1].replace("y", "i")
            c = _KANA_C.get(c, c)
            key = (c + v) if c else v
            key = {"si": "shi", "ti": "chi", "tu": "tsu", "hu": "fu", "wi": "i", "we": "e",
                   "wo": "o", "ye": "e", "yi": "i", "ri": "ri"}.get(key, key)
            if key not in KANA:
                keys = sorted(KANA)
                key = keys[_h("kana", syl) % len(keys)]
        strokes += _parse(KANA[key], ox=x)
        x += 6.6
    return strokes, max(x - 1.6, 0.0)


def _block(syl: str, ox: float):
    """One Hangul syllable block from a Latin syllable, in a 6 x 6 box at ox."""
    cons = "".join(ch for ch in syl if ch not in "aeiouy")
    vow = "".join(ch for ch in syl if ch in "aeiouy")[:1] or "eu"
    init = _HAN_C.get(syl[:1], "") if syl[:1] not in "aeiouy" else ""
    if syl[:2] == "ch":
        init = "ch"
    v = _HAN_V.get(vow, "eu")
    vs, vertical = JAMO_V[v]
    fin = _HAN_C.get(cons[-1:], "") if len(cons) > 1 and syl[-1] not in "aeiouy" else ""
    out = []
    if vertical:
        h0 = 2.2 if fin else 0.0
        out += _parse(JAMO_C[init], 3.0, 6.0 - h0 - 0.6, ox, h0 + 0.3)
        out += _parse(vs, 2.4, 6.0 - h0, ox + 3.5, h0)
    else:
        h0 = 2.0 if fin else 0.0
        top = 6.0 - h0
        out += _parse(JAMO_C[init], 3.4, top * 0.4, ox + 1.3, h0 + top * 0.58)
        out += _parse(vs, 6.0, top * 0.55, ox, h0)
    if fin:
        out += _parse(JAMO_C[fin], 3.4, 1.6, ox + 1.3, 0.0)
    return out


def _hangul(text: str):
    strokes, x = [], 0.0
    for syl in syllables(text):
        if syl == " ":
            x += 3.0
            continue
        strokes += _block(syl, x)
        x += 7.0
    return strokes, max(x - 1.0, 0.0)


def _hanzi(text: str):
    strokes, x = [], 0.0
    syl = [s for s in syllables(text) if s != " "]
    pairs = [syl[i] + (syl[i + 1] if i + 1 < len(syl) else "") for i in range(0, len(syl), 2)]
    for pr in pairs:
        h = _h("hanzi", pr)
        kind = h % 3
        if kind == 0:
            a = SIDE[(h >> 4) % len(SIDE)]
            b = WHOLE[(h >> 8) % len(WHOLE)]
            strokes += _parse(COMPONENTS[a], 2.2, 6.0, x, 0.0)
            strokes += _parse(COMPONENTS[b], 3.4, 6.0, x + 2.6, 0.0)
        elif kind == 1:
            a = TOP[(h >> 4) % len(TOP)]
            b = WHOLE[(h >> 8) % len(WHOLE)]
            strokes += _parse(COMPONENTS[a], 6.0, 2.3, x, 3.7)
            strokes += _parse(COMPONENTS[b], 5.0, 3.4, x + 0.5, 0.0)
        else:
            b = WHOLE[(h >> 8) % len(WHOLE)]
            strokes += _parse(COMPONENTS[b], 6.0, 6.0, x, 0.0)
            strokes += _parse(["0,0.5 1,0.5"], 6.0, 1.0, x, (h >> 12) % 3 * 1.0)
        x += 7.0
    return strokes, max(x - 1.0, 0.0)


def _deva(text: str):
    strokes, x = [], 0.0
    for word in text.split():
        x0 = x
        for syl in syllables(word):
            h = _h("deva", syl)
            strokes += _parse(DEVA[h % len(DEVA)], 4.0, 5.0, x, 0.0)
            if syl[-1:] == "a" and h & 16:
                strokes += _parse(["0.5,1 0.5,0"], 1.0, 5.0, x + 3.6, 0.0)
                x += 1.2
            if syl[-1:] in "ie":
                strokes += _parse(["0,1 0.4,1.35 0.9,1.2"], 3.0, 4.6, x + 0.4, 0.0)
            x += 4.6
        strokes.append([(x0 - 0.3, 5.0), (x + 0.1 - 1.0, 5.0)])
        x += 2.4
    return strokes, max(x - 2.4 - 0.9, 0.0)


SCRIPTS = {"latin": lambda t: _latin(t), "cyrillic": lambda t: _latin(t, True),
           "kana": _kana, "hangul": _hangul, "hanzi": _hanzi, "devanagari": _deva}


def layout(text: str, script: str = "latin"):
    """Strokes (lists of (x, y) in glyph units, cap height 6) and the text's width."""
    fn = SCRIPTS.get(script, SCRIPTS["latin"])
    return fn(text)


def draw(img, strokes, x0: float, y0: float, scale: float, width: float, fill) -> None:
    """Rasterize strokes onto a PIL image: glyph (x, y) to pixels (x0 + s x, y0 - s y),
    integer coordinates (the same pixels everywhere)."""
    from PIL import ImageDraw
    d = ImageDraw.Draw(img)
    w = max(1, int(round(width)))
    for pts in strokes:
        xy = [(int(round(x0 + scale * x)), int(round(y0 - scale * y))) for x, y in pts]
        if len(xy) == 1:
            xy = xy * 2
        d.line(xy, fill=fill, width=w, joint="curve")
        if w > 2:
            r = w // 2
            for px, py in (xy[0], xy[-1]):
                d.ellipse([px - r, py - r, px + r, py + r], fill=fill)


def units(text: str, script: str = "latin") -> list[str]:
    """The pieces a sign stacks one per row on a blade: letters (Latin, Cyrillic) or the
    syllables a sign stands for (two per Hanzi-like sign)."""
    if script in ("latin", "cyrillic"):
        return [ch for ch in text.upper() if ch != " "]
    syl = [s for s in syllables(text) if s != " "]
    if script == "hanzi":
        return [syl[i] + (syl[i + 1] if i + 1 < len(syl) else "") for i in range(0, len(syl), 2)]
    return syl


def unit_layout(unit: str, script: str = "latin"):
    """Strokes and width of one stacked piece."""
    if script == "hanzi":
        strokes, w = _hanzi(unit)
        return strokes, w
    return layout(unit, script)
