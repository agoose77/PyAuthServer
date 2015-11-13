from math import sqrt
from random import random

from network.utilities import look_ahead

__all__ = "quad_area", "point_in_polygon", "get_random_point"


def point_in_polygon(point, vertex_positions):
    """Determine if a point lies within a polygon defined by its vertices

    :param point: named container x, y
    :param vertex_positions: sequence of points (named container x, y)
    """
    odd_nodes = False

    x_pos = point.x
    y_pos = point.y

    for i_pos, j_pos in look_ahead(vertex_positions):
        i_y = i_pos.y
        i_x = i_pos.x
        j_y = j_pos.y
        j_x = j_pos.x
        if (i_y < y_pos <= j_y) or (j_y < y_pos <= i_y) and (i_x <= x_pos or j_x <= x_pos):
            if (i_x + (y_pos - i_y)/(j_y - i_y) * (j_x - i_x)) < x_pos:
                odd_nodes = not odd_nodes

    return odd_nodes


def quad_area(a, b, c):
    """Determine the double of the area occupied by a three vertex triangle

    :param a: named container x, y
    :param c: named container x, y
    :param b: named container x, y
    """
    side_a = b - a
    side_b = c - a

    return (side_b.x * side_a.y) - (side_a.x * side_b.y)


def get_random_point(polygon):
    """Find a random point inside a polygon

    :param polygon: polygon instance
    """
    s = random()
    t = random()

    s_area = s * polygon.area

    if len(polygon.vertices) == 3:
        p, q, r = polygon.vertices
        u = s_area / polygon.area

    else:
        area_sum = 0

        p = polygon.vertices[0]
        for i in range(2):
            # Get subtriangle vertices
            j, k, l = polygon.vertices[i: i + 3]

            # Get absolute quadrilateral (double) area
            sub_triangle_area = abs(quad_area(j, k, l)) / 2

            if area_sum >= s_area:
                u = (s_area - area_sum) / sub_triangle_area
                q, r = k, l
                break

            area_sum += sub_triangle_area

    # Find barycentric position
    v = sqrt(t)

    a = 1 - v
    b = (1 - u) * v
    c = u * v

    return a * p + b * q + c * r


def get_random_polygon(polygons):
    """Find a random polygon, with respect to area

    :param polygons: sequence of polygon objects
    """
    area_sum = 0.0
    random_polygon = None

    for polygons in polygons:
        area = polygons.area
        area_sum += area

        if (random() * area_sum) <= area:
            random_polygon = polygons

    return random_polygon