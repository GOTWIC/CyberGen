"""Deterministic elementary functions (sin, cos, exp, log, atan2, hypot, pow).

numpy's sin, cos, exp, arctan2 and power (and the platform libm behind Python's `math`) differ
in the last bits between machines: x86 builds with AVX512 use Intel SVML, ARM Macs use Apple's
libm. citygen amplifies such differences through its searches, so the generator uses these
instead. They are built only from +, -, *, /, sqrt, rint and ldexp, which IEEE 754 rounds
exactly the same way everywhere, and are accurate to a few units in the last place (fdlibm
kernels and short Taylor series after range reduction).

Each function takes a float or an array and returns the same kind.
"""

from __future__ import annotations

import numpy as np

PI = 3.141592653589793
HALF_PI = 1.5707963267948966
_PIO2_1 = 1.57079632673412561417e+00   # first 33 bits of pi/2
_PIO2_1T = 6.07710050650619224932e-11  # pi/2 - _PIO2_1
_LN2_HI = 6.93147180369123816490e-01
_LN2_LO = 1.90821492927058770002e-10
_INV_LN2 = 1.44269504088896338700e+00
_SQRT_HALF = 0.7071067811865476

_S = (-1.66666666666666324348e-01, 8.33333333332248946124e-03, -1.98412698298579493134e-04,
      2.75573137070700676789e-06, -2.50507602534068634195e-08, 1.58969099521155010221e-10)
_C = (4.16666666666666019037e-02, -1.38888888888741095749e-03, 2.48015872894767294178e-05,
      -2.75573143513906633035e-07, 2.08757232129817482790e-09, -1.13596475577881948265e-11)


def _arr(x):
    a = np.asarray(x, dtype=np.float64)
    return a, a.ndim == 0


def _out(v, scalar):
    return float(v) if scalar else v


def _ksin(r):
    z = r * r
    p = _S[4] + z * _S[5]
    p = _S[3] + z * p
    p = _S[2] + z * p
    p = _S[1] + z * p
    p = _S[0] + z * p
    return r + (r * z) * p


def _kcos(r):
    z = r * r
    p = _C[4] + z * _C[5]
    p = _C[3] + z * p
    p = _C[2] + z * p
    p = _C[1] + z * p
    p = _C[0] + z * p
    return 1.0 - 0.5 * z + (z * z) * p


def _reduce(x):
    k = np.rint(x * (2.0 / PI))
    r = (x - k * _PIO2_1) - k * _PIO2_1T
    return r, np.mod(k, 4.0)


def sin(x):
    a, sc = _arr(x)
    r, q = _reduce(a)
    s, c = _ksin(r), _kcos(r)
    v = np.where(q == 0, s, np.where(q == 1, c, np.where(q == 2, -s, -c)))
    return _out(v, sc)


def cos(x):
    a, sc = _arr(x)
    r, q = _reduce(a)
    s, c = _ksin(r), _kcos(r)
    v = np.where(q == 0, c, np.where(q == 1, -s, np.where(q == 2, -c, s)))
    return _out(v, sc)


def exp(x):
    a, sc = _arr(x)
    a = np.clip(a, -745.0, 709.0)
    k = np.rint(a * _INV_LN2)
    r = (a - k * _LN2_HI) - k * _LN2_LO
    p = np.ones_like(r)
    for n in range(13, 0, -1):  # Taylor series, |r| <= 0.35
        p = 1.0 + p * r / float(n)
    v = np.ldexp(p, k.astype(np.int64))
    return _out(v, sc)


def log(x):
    a, sc = _arr(x)
    m, e = np.frexp(a)  # a = m * 2**e, m in [0.5, 1)
    low = m < _SQRT_HALF
    m = np.where(low, m * 2.0, m)
    e = np.where(low, e - 1, e).astype(np.float64)
    s = (m - 1.0) / (m + 1.0)
    z = s * s
    p = np.full_like(s, 1.0 / 23.0)
    for n in range(21, 0, -2):  # 2 atanh(s) = log((1 + s) / (1 - s))
        p = 1.0 / n + z * p
    v = 2.0 * s * p + e * _LN2_HI + e * _LN2_LO
    return _out(v, sc)


def power(x, y):
    """x ** y for x > 0 (and 0 ** y = 0 for y > 0)."""
    a, sc = _arr(x)
    safe = np.where(a > 0, a, 1.0)
    v = np.where(a > 0, exp(y * log(safe)), 0.0)
    return _out(v, sc)


def _atan_unit(t):
    """atan(t) for |t| <= 1: three half-angle steps, then the Taylor series."""
    for _ in range(3):
        t = t / (1.0 + np.sqrt(1.0 + t * t))
    z = t * t
    # Horner form of t - t^3/3 + t^5/5 - ... ; |t| <= 0.1 after the halvings.
    q = np.full_like(t, 1.0 / 25.0)
    for n in range(23, 0, -2):
        q = 1.0 / n - z * q
    return 8.0 * t * q


def atan2(y, x):
    ya, s1 = _arr(y)
    xa, s2 = _arr(x)
    ya, xa = np.broadcast_arrays(ya, xa)
    ax, ay = np.abs(xa), np.abs(ya)
    big = ay > ax
    den = np.where(big, ay, ax)
    num = np.where(big, ax, ay)
    t = np.where(den > 0, num / np.where(den > 0, den, 1.0), 0.0)
    base = _atan_unit(t)
    base = np.where(big, HALF_PI - base, base)
    base = np.where(xa < 0, PI - base, base)
    v = np.where(ya < 0, -base, base)
    return _out(v, s1 and s2)


def hypot(x, y):
    a, s1 = _arr(x)
    b, s2 = _arr(y)
    return _out(np.sqrt(a * a + b * b), s1 and s2)


def radians(d):
    return d * (PI / 180.0)


def degrees(r):
    return r * (180.0 / PI)


def tan(x):
    return sin(x) / cos(x)


def acos(c):
    a, sc = _arr(c)
    a = np.clip(a, -1.0, 1.0)
    return _out(atan2(np.sqrt((1.0 - a) * (1.0 + a)), a), sc)


def norm(v) -> float:
    """Length of a 2D vector (no BLAS)."""
    v = np.asarray(v, dtype=np.float64)
    return float(np.sqrt(v[0] * v[0] + v[1] * v[1]))


def dot(u, v) -> float:
    """Dot product of two 2D vectors (no BLAS, so no fused multiply-add)."""
    u = np.asarray(u, dtype=np.float64)
    v = np.asarray(v, dtype=np.float64)
    return float(u[0] * v[0] + u[1] * v[1])
