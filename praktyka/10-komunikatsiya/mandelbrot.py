"""Обчислення наскрізної задачі — те саме, що у вашому 1-poslidovno.

Хочете свою версію — замініть тіло `ryadok`, але тоді й еталон порахуйте нею:
`python koordynator.py --poslidovno`.
"""

W, H = 1200, 800
MAX_ITER = 300
XMIN, XMAX = -2.0, 0.6
YMIN, YMAX = -1.2, 1.2


def ryadok(y):
    """Один рядок зображення — незалежна одиниця роботи."""
    cy = YMIN + (YMAX - YMIN) * y / H
    out = []
    for x in range(W):
        cx = XMIN + (XMAX - XMIN) * x / W
        zx = zy = 0.0
        n = 0
        while zx * zx + zy * zy <= 4.0 and n < MAX_ITER:
            zx, zy = zx * zx - zy * zy + cx, 2.0 * zx * zy + cy
            n += 1
        out.append(n)
    return out
