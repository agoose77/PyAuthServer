from collections import defaultdict

from game_system.coordinates import Vector
from game_system.geometry.utilities import point_in_polygon


class BGEPolygonStatic:

    def __init__(self, *vertices, neighbours=None):
        self.vertices = vertices
        self.position = sum(vertices, Vector()) / len(vertices)
        self.neighbours = neighbours or []

    def get_neighbours(self):
        return self.neighbours

    def __contains__(self, point):
        return point_in_polygon(point, self.vertices)

    def get_common_vertices(self, other):
        return (v for v in self.vertices if v in other.vertices)


class BGEMeshStatic:

    def __init__(self, obj):
        self._obj = obj
        self.polygons = self.build_nodes(obj.meshes[0])

    def build_polygons(self, mesh):
        points = self.get_approximate_points(mesh)

        polygons = []
        for polygon_id in range(mesh.numPolygons):
            polygon = mesh.getPolygon(polygon_id)
            positions = []
            for vertex_id in range(polygon.getNumVertex()):
                vertex_index = polygon.getVertexIndex(vertex_id)
                material_index = polygon.material_id

                point = points[material_index][vertex_index]
                positions.append(point)

            polygon = self.create_polygon(*positions)
            polygons.append(polygon)

        for polygon in polygons:
            for polygon_ in polygons:
                if polygon_ is polygon:
                    continue

                if len(list(polygon.get_common_vertices(polygon_))) > 1:
                    polygon.neighbours.append(polygon_)
                    polygon_.neighbours.append(polygon)
        return polygons

    @staticmethod
    def create_polygon(*vertices):
        return BGEPolygonStatic(*vertices)

    def get_approximate_points(self, mesh, epsilon=0.001):
        transform = self._obj.worldTransform
        material_points = {m_index: {v_index: (transform * mesh.getVertex(m_index, v_index).XYZ)
                                     for v_index in range(mesh.getVertexArrayLength(m_index))}
                           for m_index in range(len(mesh.materials))}

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