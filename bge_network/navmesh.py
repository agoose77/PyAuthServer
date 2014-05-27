from network.structures import factory_dict

from bge import types
from collections import deque, namedtuple
from functools import partial
from heapq import heappop, heappush
from itertools import islice, tee
from mathutils import Vector

from .iterators import BidirectionalIterator
from .kdtree import KDTree
from .mesh import BGEMesh


forward_vector = Vector((0, 1, 0))
EndPortal = namedtuple("EndPortal", ["left", "right"])
BoundVector = type("BoundVector", (Vector,), {"__slots__": "data"})


class PolygonKDTree(KDTree):

    def __init__(self, polygons):
        points = []
        for polygon in polygons:
            point = BoundVector(polygon.position)
            point.data = polygon
            points.append(point)

        super().__init__(points, dimensions=3)

    def find_polygon(self, point):
        _, node = self.nn_search(point)
        return node.position.data


def triangle_area_squared(a, b, c):
    ax, ay, _ = b - a
    bx, by, _ = c - a
    return (bx * ay) - (ax * by)


def look_ahead(iterable):
    items, successors = tee(iterable, 2)
    return zip(items, islice(successors, 1, None))


def manhattan_distance_heuristic(a, b):
    return (b.position - a.position).length_squared


class Portal:
    __slots__ = "source", "destination", "left", "right"

    def __init__(self, source, destination):
        self.source = source
        self.destination = destination

        self.left, self.right = self.generate_nodes()

    def generate_nodes(self):
        source_position = self.source.position
        destination_position = self.destination.position
        first, second = set(self.source.vertices).intersection(self.destination.vertices)

        side_first = triangle_area_squared(source_position, destination_position, first.position)
        side_second = triangle_area_squared(source_position, destination_position, second.position)

        mapping = {side_first: first, side_second: second}

        right = mapping[max(side_first, side_second)]
        left = mapping[min(side_first, side_second)]

        return left.position, right.position


class Funnel:
    __slots__ = "left", "right", "_apex", "_apex_callback"

    def __init__(self, apex, left, right, on_apex_changed):
        self.left = left
        self.right = right
        self._apex = apex
        self._apex_callback = on_apex_changed

    @property
    def apex(self):
        return self._apex

    @apex.setter
    def apex(self, value):
        self._apex = value
        self._apex_callback(value)

    def update(self, portals):
        portals = BidirectionalIterator(portals)
        left_index = right_index = portals.index

        # Increment index and then return entry at index
        for portal in portals:
            # Check if left is inside of left margin

            if triangle_area_squared(self.apex, self.left, portal.left) >= 0.0:
                # Check if left is inside of right margin or
                # we haven't got a proper funnel
                if self.apex == self.left or (triangle_area_squared(self.apex, self.right, portal.left) < 0.0):
                    # Narrow funnel
                    self.left = portal.left
                    left_index = portals.index

                else:
                    # Otherwise add apex to path
                    self.left = self.apex = self.right
                    # Set portal to consider from the corner we pivoted around
                    # This index is incremented by the for loop
                    portals.index = right_index
                    continue

            # Check if right is inside of right margin
            if triangle_area_squared(self.apex, self.right, portal.right) <= 0.0:
                # Check if right is inside of left margin or
                # we haven't got a proper funnel
                if self.apex == self.right or (triangle_area_squared(self.apex, self.left, portal.right) > 0.0):
                    # Narrow funnel
                    self.right = portal.right
                    right_index = portals.index

                else:
                    # Otherwise add apex to path
                    self.right = self.apex = self.left
                    # Set portal to consider from the corner we pivoted around
                    # This index is incremented by the for loop
                    portals.index = left_index
                    continue


class PathNotFoundException(Exception):
    pass


class AlgorithmNotImplementedException(Exception):
    pass


class AStarAlgorithm:

    def __init__(self):
        self.heuristic = manhattan_distance_heuristic

    @staticmethod
    def reconstruct_path(node, path):
        result = deque()
        while node:
            result.appendleft(node)
            node = path.get(node)
        return result

    def find_path(self, start, destination, nodes):
        open_set = {start}
        closed_set = set()

        f_scored = [(0, start)]
        g_scored = {start: 0}

        heuristic_function = self.heuristic
        path = {}

        while open_set:
            current = heappop(f_scored)[1]
            if current is destination:
                return self.reconstruct_path(destination, path)

            open_set.remove(current)
            closed_set.add(current)

            for neighbour in current.get_neighbours():
                if neighbour in closed_set:
                    continue

                tentative_g_score = g_scored[current] + (neighbour.position - current.position).length_squared

                if not neighbour in open_set or tentative_g_score < g_scored[neighbour]:
                    path[neighbour] = current
                    g_scored[neighbour] = tentative_g_score
                    heappush(f_scored, (tentative_g_score + heuristic_function(neighbour, destination), neighbour))

                    if not neighbour in open_set:
                        open_set.add(neighbour)

        raise PathNotFoundException("Couldn't find path for given points")


class FunnelAlgorithm:

    def __init__(self):
        self.portals = factory_dict(lambda x: Portal(*x), provide_key=True)

    def get_portal(self, previous_node, node):
        return self.portals[(previous_node, node)]

    def find_path(self, source, destination, nodes):
        path = [source]
        get_portal = self.get_portal

        # Account for main path
        portals = [get_portal(source, destination) for source, destination in look_ahead(nodes)]
        portals.append(EndPortal(destination, destination))

        funnel = Funnel(source, source, source, path.append)
        funnel.update(portals)

        # Account for last destination point
        if funnel is None:
            return []

        path.append(destination)
        return path


class PathfinderAlgorithm:

    def __init__(self, low_fidelity, high_fidelity, spatial_lookup):
        self.low_resolution = low_fidelity
        self.high_resolution = high_fidelity
        self.spatial_lookup = spatial_lookup

    def find_path(self, source, destination, nodes, low_resolution=False):
        source_node = self.spatial_lookup(source)
        destination_node = self.spatial_lookup(destination)

        try:
            path_finder = self.low_resolution.find_path

        except AttributeError:
            raise AlgorithmNotImplementedException("Couldn't find low resolution finder algorithm")

        low_resolution_path = path_finder(source_node, destination_node, nodes)
        if low_resolution:
            return low_resolution_path

        try:
            path_finder = self.high_resolution.find_path

        except AttributeError:
            raise AlgorithmNotImplementedException("Couldn't find high resolution finder algorithm")

        high_resolution_path = path_finder(source, destination, low_resolution_path)
        return high_resolution_path


class NavmeshProxy(types.KX_NavMeshObject):

    def find_polygon(self, point):
        for p in self.mesh.polygons:
            if point in p:
                return p

    def __init__(self, obj):
        self.mesh = BGEMesh(self)
        self.polygon_lookup = PolygonKDTree(self.mesh.polygons)

        astar = AStarAlgorithm()
        funnel = FunnelAlgorithm()
        finder_algorithm = PathfinderAlgorithm(astar, funnel, self.find_polygon)

        self.find_path = partial(finder_algorithm.find_path, nodes=self.mesh.polygons)
