from functools import lru_cache

from game_system.geometry.utilities import quad_area

from .static import BGEMeshStatic, BGEPolygonStatic


class BGENodePortal:
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


class BGENavmeshNode(BGEPolygonStatic):

    @lru_cache()
    def get_portal_to(self, other):
        return BGENodePortal(self, other)


class BGENavmesh(BGEMeshStatic):

    def find_node(self, point):
        for polygon in self.polygons:
            if point in polygon:
                return polygon

    @staticmethod
    def create_polygon(*vertices):
        return BGENavmeshNode(*vertices)