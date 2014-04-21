from bge import types
from collections import defaultdict, namedtuple 
from functools import partial
from heapq import heappop, heappush
from itertools import islice, tee
from mathutils import Vector

from .kdtree import KDTree


forward_vector = Vector((0, 1, 0))
EndPortal = namedtuple("EndPortal", ["left", "right"])
BoundVector = type("BoundVector", (Vector,), {"__slots__": "data"})


def triangle_area_squared(a, b, c):
    ax, ay, _ = b - a
    bx, by, _ = c - a
    return (bx * ay) - (ax * by)


def look_ahead(iterable):
    items, successors = tee(iterable, 2)
    return zip(items, islice(successors, 1, None))


def manhattan_distance_heureustic(a, b):
    return (b.position - a.position).length_squared


class bidirectional_iter:
    def __init__(self, collection):
        self.collection = collection
        self.index = -1

    def __next__(self):
        try:
            self.index += 1
            result = self.collection[self.index]
        except IndexError:
            raise StopIteration
        return result

    def __prev__(self):
        self.index -= 1
        if self.index < 0:
            raise StopIteration
        return self.collection[self.index]

    def __iter__(self):
        return self


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
        return (first, second) if first_local.x < second_local.x else (second, first)


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
        portals = bidirectional_iter(portals_list)
        left_index = right_index = portals.index

        # Increment index and then return entry at index
        for portal in portals:
            # Check if left is inside of left margin
            if triangle_area_squared(self.apex, self.left, portal.left) >= 0.0:
                # Check if left is inside of right margin or we haven't got a proper funnel
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
                # Check if right is inside of left margin or we haven't got a proper funnel
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
        open = {start}
        closed = set()

        f_scored = [(0, start)]
        g_scored = {start: 0}

        heureustic = self.heureustic
        path = {}

        while open:
            current = heappop(f_scored)[1]
            if current is destination:
                return self.reconstruct_path(destination, path)

            open.remove(current)
            closed.add(current)

            for neighbour in current.neighbours:
                if neighbour in closed:
                    continue

                tentative_g_score = g_scored[current] + (neighbour.position -
                                            current.position).length_squared

                if (not neighbour in open or tentative_g_score
                            < g_scored[neighbour]):
                    path[neighbour] = current
                    g_scored[neighbour] = tentative_g_score

                    heappush(f_scored, (tentative_g_score +
                             heureustic(neighbour, destination), neighbour))

                    if not neighbour in open:
                        open.add(neighbour)

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
        funnel = None

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
        source_node = self.spatial_lookup.find_node(source)
        destination_node = self.spatial_lookup.find_node(destination)

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


class NavigationNode:

    def __init__(self, *vertices, neighbours=None):
        self.vertices = vertices
        self.position = sum(vertices, Vector()) / len(vertices)
        self.neighbours = neighbours or []

    def get_common_vertices(self, other):
        return (v for v in self.vertices if v in other.vertices)


class BGENavigationMesh:

    def __init__(self, obj):
        self._obj = obj
        self.mesh_nodes = {mesh_index: self.build_nodes(mesh) for mesh_index,
                          mesh in enumerate(obj.meshes)}

    def build_nodes(self, mesh):
        points = self.get_approximate_points(mesh)

        nodes = []
        for polygon_id in range(mesh.numPolygons):
            polygon = mesh.getPolygon(polygon_id)
            positions = []
            for vertex_id in range(polygon.getNumVertex()):
                vertex_index = polygon.getVertexIndex(vertex_id)
                material_index = polygon.material_id

                point = points[material_index][vertex_index]
                positions.append(point)

            node = NavigationNode(*positions)
            nodes.append(node)

        found_neighbours = set()
        for node in nodes:
            for node_ in nodes:
                if node_ is node:
                    continue
                if len(list(node.get_common_vertices(node_))) > 1:
                    node.neighbours.append(node_)
                    node_.neighbours.append(node)
        return nodes

    def get_approximate_points(self, mesh, epsilon=0.001):
        transform = self._obj.worldTransform
        material_points = {m_index: {v_index: (transform *
                                    mesh.getVertex(m_index, v_index).XYZ)
                            for v_index in range(
                                        mesh.getVertexArrayLength(m_index))}
                            for m_index in range(
                                        len(mesh.materials))}

        material_unique = defaultdict(dict)

        for material, points in material_points.items():
            unique_points = material_unique[material]
            for point_id, point in points.items():
                if point_id in unique_points:
                    continue

                # Choose one and associate all others with it
                unique_points[point_id] = point
                for point_id_, point_ in points.items():
                    if (point_ - point).length_squared < epsilon:
                        unique_points[point_id_] = point
        return material_unique


class SpatialTree(KDTree):

    def __init__(self, polygons):
        points = []
        for polygon in polygons:
            point = BoundVector(polygon.position)
            point.data = polygon
            points.append(point)

        super().__init__(points, dimensions=3)

    def find_node(self, point):
        distance, node = self.nn_search(point)
        return node.position.data


class NavmeshProxy(types.KX_GameObject):

    def __init__(self, obj):
        self.mesh = BGENavigationMesh(self)
        self.polygons = self.mesh.mesh_nodes[0]
        self.spatial_lookup = SpatialTree(self.polygons)

        astar = AStarAlgorithm()
        funnel = FunnelAlgorithm()
        finder_algorithm = PathfinderAlgorithm(astar, funnel,
                                            self.spatial_lookup)

        self.find_path = partial(finder_algorithm.find_path,
                                    nodes=self.polygons)
