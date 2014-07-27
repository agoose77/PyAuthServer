__all__ = ["triangle_area_squared", "point_in_polygon"]


def point_in_polygon(point, vertex_positions):
    """Determine if a point lies within a polygon defined by its vertices

    :param point: named container x, y
    :param vertex_positions: sequence of points
    """
    vertex_count = len(vertex_positions)
    j = vertex_count - 1
    odd_nodes = False
    x_pos, y_pos, *_ = point

    for i, i_pos in enumerate(vertex_positions):
        j_pos = vertex_positions[j]
        if (i_pos.y < y_pos <= j_pos.y) or (j_pos.y < y_pos <= i_pos.y) and (i_pos.x <= x_pos or j_pos.x <= x_pos):
            if (i_pos.x + (y_pos - i_pos.y)/(j_pos.y - i_pos.y) * (j_pos.x - i_pos.x)) < x_pos:
                odd_nodes = not odd_nodes
        j = i

    return odd_nodes


def triangle_area_squared(a, b, c):
    """Determine the area occupied by a three vertex triangle

    :param a: named container x, y
    :param c: named container x, y
    :param b: named container x, y
    """
    ax, ay, *_ = b - a
    bx, by, *_ = c - a
    return (bx * ay) - (ax * by)