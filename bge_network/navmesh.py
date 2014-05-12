from bge import types
from collections import defaultdict, namedtuple 
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

    def find_node(self, point):
        _, node = self.nn_search(point)
        return node.position.data


def triangle_area_squared(a, b, c):
    ax, ay, _ = b - a
    bx, by, _ = c - a
    return (bx * ay) - (ax * by)


def look_ahead(iterable):
    items, successors = tee(iterable, 2)
    return zip(items, islice(successors, 1, None))


def manhattan_distance_heureustic(a, b):
    return (b.position - a.position).length_squared


class Portal:
    __slots__ = "source", "destination", "left", "right"

    def __init__(self, source, destination):
        self.source = source
        self.destination = destination

        self.left, self.right = self.generate_nodes()

    def generate_nodes(self):
        direction = (self.destination.position - self.source.position)
        rotation = direction.rotation_difference(forward_vector)
        first, second = self.source.get_common_vertices(self.destination)
        first_local = first.copy()
        first_local.rotate(rotation)
        second_local = second.copy()
        second_local.rotate(rotation)
        return (first, second) if first_local.x < second_local.x \
            else (second, first)


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
        portals_list = list(portals)
        portals = BidirectionalIterator(portals_list)
        left_index = right_index = portals.index

        # Increment index and then return entry at index
        for portal in portals:
            # Check if left is inside of left margin
            if triangle_area_squared(self.apex, self.left, portal.left) >= 0.0:
                # Check if left is inside of right margin or
                # we haven't got a proper funnel
                if (self.apex == self.left) or (triangle_area_squared(
                                self.apex, self.right, portal.left)) < 0.0:
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
            if triangle_area_squared(self.apex, self.right,
                                    portal.right) <= 0.0:
                # Check if right is inside of left margin or
                # we haven't got a proper funnel
                if (self.apex == self.right) or (triangle_area_squared(
                                self.apex, self.left, portal.right)) > 0.0:
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
        self.heureustic = manhattan_distance_heureustic

    def reconstruct_path(self, node, path):
        result = []
        while node:
            result.append(node)
            node = path.get(node)
        return reversed(result)

    def find_path(self, start, destination, nodes):
        open_set = {start}
        closed_set = set()

        f_scored = [(0, start)]
        g_scored = {start: 0}

        heureustic = self.heureustic
        path = {}

        while open_set:
            current = heappop(f_scored)[1]
            if current is destination:
                return self.reconstruct_path(destination, path)

            open_set.remove(current)
            closed_set.add(current)

            for neighbour in current.neighbours:
                if neighbour in closed_set:
                    continue

                tentative_g_score = g_scored[current] + (neighbour.position -
                                            current.position).length_squared

                if (not neighbour in open_set or tentative_g_score
                            < g_scored[neighbour]):
                    path[neighbour] = current
                    g_scored[neighbour] = tentative_g_score

                    heappush(f_scored, (tentative_g_score +
                             heureustic(neighbour, destination), neighbour))

                    if not neighbour in open_set:
                        open_set.add(neighbour)

        raise PathNotFoundException("Couldn't find path for given points")


class FunnelAlgorithm:

    def __init__(self):
        self.portals = defaultdict(dict)

    def get_portal(self, previous_node, node):
        portals = self.portals[previous_node]
        try:
            return portals[node]
        except KeyError:
            portal = portals[node] = Portal(previous_node, node)
            return portal

    def find_path(self, source, destination, nodes):
        path = [source]

        get_portal = self.get_portal

        # Account for main path
        portals = [get_portal(previous_node, node) for previous_node,
                                   node in look_ahead(nodes)]
        portals.append(EndPortal(destination, destination))

        funnel = Funnel(source, portals[0].left, portals[0].right, path.append)
        funnel.update(portals.__iter__())

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

    def find_path(self, source, destination, nodes):
        source_node = self.spatial_lookup(source)
        destination_node = self.spatial_lookup(destination)

        try:
            path_finder = self.low_resolution.find_path
        except AttributeError:
            raise AlgorithmNotImplementedException("Couldn't find low \
                                resolution finder algorithm")

        low_resolution_path = path_finder(source_node, destination_node, nodes)

        try:
            path_finder = self.high_resolution.find_path
        except AttributeError:
            raise AlgorithmNotImplementedException("Couldn't find high \
                                resolution finder algorithm")

        high_resolution_path = path_finder(source, destination,
                                        low_resolution_path)
        return high_resolution_path


class NavmeshProxy(types.KX_GameObject):

    def __init__(self, obj):
        self.mesh = BGEMesh(self.meshes[0])
        self.polygon_lookup = PolygonKDTree(self.mesh.polygons)

        astar = AStarAlgorithm()
        funnel = FunnelAlgorithm()
        finder_algorithm = PathfinderAlgorithm(astar, funnel,
                                            self.polygon_lookups.find_polygon)

        self.find_path = partial(finder_algorithm.find_path,
                                    nodes=self.polygons)
