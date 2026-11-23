"""Small reusable math helpers."""

def clamp(x, lo, hi):
    return lo if x < lo else hi if x > hi else x


def smoothstep(x):
    x = clamp(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)
