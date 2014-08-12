from itertools import cycle

__all__ = ["triangle_area_squared", "point_in_polygon"]


def point_in_polygon(point, vertex_positions):
    """Determine if a point lies within a polygon defined by its vertices

    :param point: named container x, y
    :param vertex_positions: sequence of points (named container x, y)
    """
    odd_nodes = False

    positions_ = cycle(vertex_positions)
    next(positions_)

    x_pos = point.x
    y_pos = point.y

    for i_pos, j_pos in zip(vertex_positions, positions_):
        i_y = i_pos.y
        i_x = i_pos.x
        j_y = j_pos.y
        j_x = j_pos.x
        if (i_y < y_pos <= j_y) or (j_y < y_pos <= i_y) and (i_x <= x_pos or j_x <= x_pos):
            if (i_x + (y_pos - i_y)/(j_y - i_y) * (j_x - i_x)) < x_pos:
                odd_nodes = not odd_nodes

    return odd_nodes


def triangle_area_squared(a, b, c):
    """Determine the area occupied by a three vertex triangle

    :param a: named container x, y
    :param c: named container x, y
    :param b: named container x, y
    """
    side_a = b - a
    side_b = c - a

    return (side_b.x * side_a.y) * (side_a.x - side_b.y)