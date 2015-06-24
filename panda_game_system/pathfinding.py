from game_system.geometry.utilities import quad_area, point_in_polygon

from network.utilities import mean

from functools import lru_cache


class PandaPolygon:

    def __init__(self, vertices):
        self.neighbours = set()

        self.position = None
        self.vertices = vertices
        self.position = mean(vertices)

        # Store area
        if len(vertices) == 3:
            self.area = abs(quad_area(*vertices)) / 2

        # Store area and area of individual triangles
        else:
            area_a = quad_area(*vertices[:3])
            area_b = quad_area(*vertices[1:])
            self.area = abs(area_a + area_b) / 2

    def __contains__(self, point):
        return point_in_polygon(point, self.vertices)


class PandaNodePortal:
    __slots__ = "source", "destination", "left", "right"

    def __init__(self, source, destination):
        self.source = source
        self.destination = destination

        self.left, self.right = self._generate_nodes()

    def _generate_nodes(self):
        source_position = self.source.position
        destination_position = self.destination.position
        first, second = [v for v in self.source.vertices if v in self.destination.vertices]

        side_first = quad_area(source_position, destination_position, first)
        side_second = quad_area(source_position, destination_position, second)

        mapping = {side_first: first, side_second: second}

        right = mapping[max(side_first, side_second)]
        left = mapping[min(side_first, side_second)]

        return left, right


class PandaNavmeshNode(PandaPolygon):

    @lru_cache()
    def get_portal_to(self, other):
        return PandaNodePortal(self, other)