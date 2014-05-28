def triangle_area_squared(a, b, c):
    ax, ay, _ = b - a
    bx, by, _ = c - a
    return (bx * ay) - (ax * by)