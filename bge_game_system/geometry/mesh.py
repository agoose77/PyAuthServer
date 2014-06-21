from collections import Counter
from functools import lru_cache

from mathutils import Vector, geometry

from game_system.geometry.mesh import IVertex, IPolygon
from .kdtree import KDTree
from ..game_system.utilities.math import mean
from ..bge_network.geometry.geometry import point_in_polygon


__all__ = ['BGEPolygon', 'BGEVertexTree', 'BGEVertexGroup', 'BoundVector',
           'BGEMesh']


BoundVector = type("BoundVector", (Vector,), {"__slots__": "data"})


class BGEVertexGroup(IVertex):

    __slots__ = ['_members', '_get_transform', '_colour', '_normal', '_position', '_uv', '_polygons']

    def __init__(self, members, get_transform):
        self._members = members
        self._get_transform = get_transform

        self._colour = self._get_colour()
        self._normal = self._get_normal()
        self._polygons = []
        self._position = self._get_position()
        self._uv = self._get_uv()

    def _get_colour(self):
        return mean(m.color for m in self._members)

    def _get_normal(self):
        return self._get_transform() * mean(m.normal for m in self._members)

    def _get_position(self):
        return self._get_transform() * mean(m.XYZ for m in self._members)

    def _get_uv(self):
        return mean(m.UV for m in self._members)

    @property
    def colour(self):
        return self._colour.copy()

    @colour.setter
    def colour(self, colour):
        difference = colour - self._colour
        for vertex in self._members:
            vertex.colour += difference
        self._colour += difference

    @property
    def normal(self):
        return self._normal.copy()

    @normal.setter
    def normal(self, normal):
        difference = normal - self._normal
        inverted_difference = self._get_transform().inverted() * difference
        for vertex in self._members:
            vertex.normal += inverted_difference
        self._normal += difference

    @property
    def polygons(self):
        return self._polygons

    @property
    def position(self):
        return self._position.copy()

    @position.setter
    def position(self, position):
        difference = position - self._position
        inverted_difference = self._get_transform().inverted() * difference

        for vertex in self._members:
            vertex.setXYZ(vertex.getXYZ() + inverted_difference)

        self._position += difference

    @property
    def uv(self):
        return self._uv.copy()

    @uv.setter
    def uv(self, uv):
        difference = uv - self._uv
        for vertex in self._members:
            vertex.UV += difference
        self._uv += difference


class BGEPolygon(IPolygon):

    __slots__ = ['_vertices']

    def __init__(self, vertices):
        self._vertices = vertices

        # Register as a polygon
        for vertex in self._vertices:
            vertex.polygons.append(self)

    def __contains__(self, point):
        vertex_positions = [v._position for v in self._vertices]
        return point_in_polygon(point, vertex_positions)

    def __lt__(self, other):
        return self.area < other.area

    @lru_cache()
    def get_neighbours(self, shared_vertices=2):
        neighbour_counts = Counter([p for v in self._vertices for p in v.polygons if not p is self])
        return [p for p, c in neighbour_counts.items() if c == shared_vertices]

    @property
    def area(self):
        points = [v._position for v in self._vertices]
        first_tri = points[:3]

        area_first = geometry.area_tri(*first_tri)

        # For quads
        if len(first_tri) <= 3:
            return area_first

        second_tri = points[1:]
        return area_first + geometry.area_tri(*second_tri)

    @property
    def normal(self):
        return geometry.normal(*[x._position for x in self._vertices])

    @property
    def vertices(self):
        return self._vertices

    @property
    def position(self):
        return mean([m._position for m in self._vertices])

    @position.setter
    def position(self, position):
        difference = position - self._position
        for vertex in self._vertices:
            vertex.position += difference


class BGEVertexTree(KDTree):

    def __init__(self, vertices):
        points = []

        for vertex in vertices:
            point = BoundVector(vertex.XYZ)
            point.data = vertex

            points.append(point)

        super().__init__(points, dimensions=3)

    def find_vertex(self, point):
        _, node = self.nn_search(point)

        return node.position.data

    def find_vertices(self, point, search_range=0.01):
        try:
            _, nodes = zip(*self.nn_range_search(point, search_range))

        except ValueError:
            return []

        return [n.position.data for n in nodes]


class BGEMesh:

    def __init__(self, bge_obj, mesh_index=0):
        bge_mesh = bge_obj.meshes[mesh_index]

        self._get_transform = lambda: bge_obj.worldTransform
        self._polygons = self._convert_polygons(bge_mesh)

    @property
    def polygons(self):
        return self._polygons

    @property
    def vertices(self):
        return set(v for poly in self._polygons for v in poly.vertices)

    @staticmethod
    def _build_temporary_data(mesh):
        """Construct dictionary representation of mesh structure"""

        for p_index in range(mesh.numPolygons):
            polygon = mesh.getPolygon(p_index)
            polygon_vertices = polygon.getNumVertex()
            material_id = polygon.material_id

            vertices = []
            for poly_v_index in range(polygon_vertices):
                v_index = polygon.getVertexIndex(poly_v_index)
                vertex = mesh.getVertex(material_id, v_index)
                vertices.append(vertex)

            yield vertices

    def _convert_polygons(self, bge_mesh):
        bge_polygon_vertices = self._build_temporary_data(bge_mesh)

        vertex_tree = BGEVertexTree(self._get_all_vertices(bge_mesh))
        get_similar_vertices = vertex_tree.find_vertices

        converted_vertices = {}
        get_vertex = converted_vertices.__getitem__
        set_vertex = converted_vertices.__setitem__

        polygons = []
        add_polygon = polygons.append

        for vertices in bge_polygon_vertices:
            polygon_vertices = []
            add_vertex = polygon_vertices.append

            for vertex in vertices:
                shared_vertices = get_similar_vertices(vertex.XYZ)
                lookup = frozenset(x.XYZ[:] for x in shared_vertices)

                try:
                    bge_vertex = get_vertex(lookup)

                except KeyError:
                    bge_vertex = BGEVertexGroup(shared_vertices, self._get_transform)
                    set_vertex(lookup, bge_vertex)

                add_vertex(bge_vertex)

            polygon = BGEPolygon(polygon_vertices)
            add_polygon(polygon)

        return polygons

    @staticmethod
    def _get_all_vertices(mesh):
        for m_index in range(len(mesh.materials)):
            for v_index in range(mesh.getVertexArrayLength(m_index)):
                yield mesh.getVertex(m_index, v_index)
