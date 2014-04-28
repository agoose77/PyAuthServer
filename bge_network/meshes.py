from collections import defaultdict
from mathutils import Vector

from .kdtree import KDTree

__all__ = ['Polygon', 'PolygonMesh', 'PolygonTree', 'BoundVector']


BoundVector = type("BoundVector", (Vector,), {"__slots__": "data"})


class PolygonTree(KDTree):

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


class Polygon:

    def __init__(self, *vertices, neighbours=None):
        self.vertices = vertices
        self.position = sum(vertices, Vector()) / len(vertices)
        self.neighbours = neighbours or []

    def get_common_vertices(self, other):
        return (v for v in self.vertices if v in other.vertices)


class PolygonMesh:

    def __init__(self, obj):
        self._obj = obj
        self.mesh_polygons = {mesh_index: self._build_polygons(mesh)
                              for mesh_index, mesh in enumerate(obj.meshes)}

    def _build_polygons(self, mesh):
        points = self._get_approximate_points(mesh)

        nodes = []
        for polygon_id in range(mesh.numPolygons):
            polygon = mesh.getPolygon(polygon_id)
            positions = []
            for vertex_id in range(polygon.getNumVertex()):
                vertex_index = polygon.getVertexIndex(vertex_id)
                material_index = polygon.material_id

                point = points[material_index][vertex_index]
                positions.append(point)

            node = Polygon(*positions)
            nodes.append(node)

        for node in nodes:
            for node_ in nodes:
                if node_ is node:
                    continue
                if len(list(node.get_common_vertices(node_))) > 1:
                    node.neighbours.append(node_)
                    node_.neighbours.append(node)
        return nodes

    def _get_approximate_points(self, mesh, epsilon=0.001):
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
