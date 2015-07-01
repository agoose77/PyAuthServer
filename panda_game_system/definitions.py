from network.decorators import with_tag
from network.signals import SignalListener
from network.tagged_delegate import FindByTag

from game_system.animation import Animation
from game_system.pathfinding.algorithm import NavmeshAStarAlgorithm, FunnelAlgorithm, NavigationPath
from game_system.coordinates import Euler, Vector
from game_system.definitions import ComponentLoader, ComponentLoaderResult
from game_system.geometry.kdtree import KDTree
from game_system.geometry.utilities import get_random_point, get_random_polygon
from game_system.enums import AnimationMode, AnimationBlend, Axis, CollisionState, CollisionGroups, PhysicsType
from game_system.physics import RayTestResult
from game_system.signals import CollisionSignal, UpdateCollidersSignal
from game_system.resources import ResourceManager

from .pathfinding import PandaNavmeshNode
from .signals import RegisterPhysicsNode, DeregisterPhysicsNode

from contextlib import contextmanager
from math import radians, degrees
from os import path
from operator import methodcaller

from panda3d.bullet import BulletRigidBodyNode, BulletTriangleMeshShape, BulletTriangleMesh
from panda3d.core import Filename, Vec3, GeomVertexReader, BitMask32, NodePath, Point3, BoundingSphere


def entity_from_nodepath(nodepath):
    if not nodepath.has_python_tag("entity"):
        return None

    return nodepath.get_python_tag("entity")


get_hit_fraction = methodcaller("get_hit_fraction")


class BoundVector(Vector):
    """Vector subclass with data member.

    Used in KDTree to associate node with position
    """

    data = None


class PandaParentableBase:

    def __init__(self, nodepath):
        self._nodepath = nodepath
        self.children = set()


class PandaSocket(PandaParentableBase):
    """Attachment socket interface"""

    def __init__(self, name, parent, nodepath):
        super().__init__(nodepath)

        self.name = name
        self._parent = parent

    @property
    def world_position(self):
        return Vector(self._nodepath.getPos(base.render))

    @property
    def world_orientation(self):
        h, p, r = self._nodepath.getHpr(base.render)
        return Euler((radians(p), radians(r), radians(h)))


class PandaComponent(FindByTag):
    """Base class for Panda component"""

    subclasses = {}

    def destroy(self):
        """Destroy component"""
        pass


@with_tag("animation")
class PandaAnimationInterface(PandaComponent):

    def __init__(self, config_section, entity, nodepath):
        self._nodepath = nodepath
        self._entity = entity

        # Set transform relationship

        self._actor = nodepath.get_python_tag("actor")

    def play(self, name, loop=False):
        if loop:
            self._actor.loop(name)

        else:
            self._actor.play(name)

        return self._actor.getAnimControl(name)


@with_tag("physics")
class PandaPhysicsInterface(PandaComponent):

    def __init__(self, config_section, entity, nodepath):
        self._nodepath = nodepath
        self._entity = entity
        self._node = self._nodepath.node()

        # Set transform relationship
        self._registered_nodes = list(nodepath.find_all_matches("**/+BulletRigidBodyNode"))

        if isinstance(self._node, BulletRigidBodyNode):
            self._registered_nodes.append(self._node)

        for node in self._registered_nodes:
            RegisterPhysicsNode.invoke(node)

        self._node.notify_collisions(True)
        self._node.set_deactivation_enabled(False)

        self._suspended_mass = None
        self._collision_group = CollisionGroups.geometry

    def destroy(self):
        for child in self._registered_nodes:
            DeregisterPhysicsNode.invoke(child)

    def ray_test(self, target, source=None, distance=None, ignore_self=True, mask=None):
        """Perform a ray trace to a target

        :param target: target to trace towards
        :param source: optional origin of trace, otherwise object position
        :param distance: distance to use instead of vector length
        :rtype: :py:class:`game_system.physics.RayTestResult`
        """
        if source is None:
            source = Vector(self._nodepath.getPos(base.render))

        # Move target to appropriate position, if explicit distance
        if distance:
            direction = target - source
            direction.length = distance

            target = source + direction

        if mask is None:
            collision_mask = BitMask32.all_on()

        else:
            collision_mask = BitMask32()
            collision_mask.set_word(mask)

        world = self._node.get_python_tag("world")

        query_result = world.rayTestAll(tuple(source), tuple(target), collision_mask)
        sorted_hits = sorted(query_result.get_hits(), key=get_hit_fraction)

        for hit_result in sorted_hits:
            hit_node = hit_result.get_node()

            hit_entity = entity_from_nodepath(hit_node)

            if ignore_self and hit_entity is self._entity:
                continue

            hit_position = Vector(hit_result.get_hit_pos())
            hit_distance = (hit_position - source).length
            hit_normal = Vector(hit_result.get_hit_normal())

            return RayTestResult(hit_position, hit_normal, hit_entity, hit_distance)

    @property
    def collision_group(self):
        return self._collision_group

    @collision_group.setter
    def collision_group(self, group):
        self._collision_group = group

    @property
    def collision_mask(self):
        return self._collision_group

    @collision_mask.setter
    def collision_mask(self, group):
        self._collision_group = group

    @property
    def type(self):
        return PhysicsType.dynamic

    @property
    def suspended(self):
        return self._suspended_mass is not None

    @suspended.setter
    def suspended(self, value):
        if value == self.suspended:
            return

        if value:
            self._suspended_mass = self._node.get_mass()
            self._node.set_mass(0.0)

        else:
            self._node.set_mass(self._suspended_mass)
            self._suspended_mass = None

    @property
    def mass(self):
        if self.suspended:
            return self._suspended_mass

        else:
            return self._node.get_mass()

    @mass.setter
    def mass(self, value):
        if self.suspended:
            self._suspended_mass = value

        else:
            self._node.set_mass(value)

    @property
    def is_colliding(self):
        return bool(self._level_manager)

    @property
    def world_velocity(self):
        return Vector(self._node.getLinearVelocity())

    @world_velocity.setter
    def world_velocity(self, velocity):
        self._node.setLinearVelocity(tuple(velocity))

    @property
    def world_angular(self):
        return Vector(self._node.getAngularVelocity())

    @world_angular.setter
    def world_angular(self, angular):
        self._node.setAngularVelocity(tuple(angular))

    @property
    def local_velocity(self):
        parent = self._nodepath.getParent()

        inverse_rotation = parent.getQuat()
        inverse_rotation.invertInPlace()

        velocity = self._node.getLinearVelocity()
        inverse_rotation.xform(velocity)

        return Vector(velocity)

    @local_velocity.setter
    def local_velocity(self, velocity):
        velocity_ = Vec3(*velocity)
        parent = self._nodepath.getParent()

        rotation = parent.getQuat()
        rotation.xform(velocity_)

        self._node.setLinearVelocity(velocity_)

    @property
    def local_angular(self):
        parent = self._nodepath.getParent()

        inverse_rotation = parent.getQuat()
        inverse_rotation.invertInPlace()

        angular = self._node.getAngularVelocity()
        inverse_rotation.xform(angular)

        return Vector(angular)

    @local_angular.setter
    def local_angular(self, angular):
        angular_ = Vec3(*angular)
        parent = self._nodepath.getParent()

        rotation = parent.getQuat()
        rotation.xform(angular_)

        self._node.setAngularVelocity(angular_)


@with_tag("transform")
class PandaTransformInterface(PandaComponent, SignalListener, PandaParentableBase):
    """Transform implementation for Panda entity"""

    def __init__(self, config_section, entity, nodepath):
        super().__init__(nodepath)

        self._entity = entity

        self.sockets = self.create_sockets(nodepath)
        self._parent = None

        self.register_signals()

    @property
    def parent(self):
        return self._parent

    @parent.setter
    def parent(self, parent):
        current_parent = self._parent
        if parent is current_parent:
            return

        if current_parent is not None:
            current_parent.children.remove(self._nodepath)

        if parent is None:
            self._nodepath.wrtReparentTo(base.render)
            return

        if not isinstance(parent, PandaParentableBase):
            raise TypeError("Invalid parent type {}".format(parent.__class__.__name__))

        self._nodepath.wrtReparentTo(parent._nodepath)

        parent.children.add(self._nodepath)
        self._parent = parent

    def create_sockets(self, nodepath):
        sockets = {}

        for child_nodepath in nodepath.find_all_matches("**/=socket"):
            socket_name = child_nodepath.get_name()
            socket = PandaSocket(socket_name, self, nodepath)
            sockets[socket_name] = socket

        return sockets

    @property
    def world_position(self):
        return Vector(self._nodepath.getPos(base.render))

    @world_position.setter
    def world_position(self, position):
        self._nodepath.setPos(base.render, *position)

    @property
    def world_orientation(self):
        h, p, r = self._nodepath.getHpr(base.render)
        return Euler((radians(p), radians(r), radians(h)))

    @world_orientation.setter
    def world_orientation(self, orientation):
        p, r, h = orientation
        self._nodepath.setHpr(base.render, degrees(h), degrees(p), degrees(r))

    def align_to(self, vector, factor=1, axis=Axis.y):
        """Align object to vector

        :param vector: direction vector
        :param factor: slerp factor
        :param axis: alignment direction
        """
        if not vector.length_squared:
            return

        forward_axis = Axis[axis].upper()

        rotation_quaternion = vector.to_track_quat(forward_axis, "Z")
        current_rotation = self.world_orientation.to_quaternion()
        self.world_orientation = current_rotation.slerp(rotation_quaternion, factor).to_euler()

    def get_direction_vector(self, axis):
        """Get the axis vector of this object in world space

        :param axis: :py:class:`game_system.enums.Axis` value
        :rtype: :py:class:`game_system.coordinates.Vector`
        """
        direction = Vec3(0, 0, 0)
        direction[axis] = 1

        rotation = self._nodepath.getQuat()
        direction = rotation.xform(direction)

        return Vector(direction)


@with_tag("navmesh")
class PandaNavmeshInterface(PandaComponent):

    def __init__(self, config_section, entity, nodepath):
        super().__init__()

        self._entity = entity
        #nodepath.hide()

        nodepath.set_render_mode_wireframe()

        # Get navmesh data
        geom_nodepath = nodepath.find('**/+GeomNode')
        geom_node = geom_nodepath.node()
        geom = geom_node.get_geom(0)

        self.nodes = self._parse_geom(geom)
        self.kd_tree = self._create_kd_tree(self.nodes)

        self._bullet_nodepath = self._create_bullet_nodepath(geom, geom_node, entity)
        RegisterPhysicsNode.invoke(self._bullet_nodepath.node())

        self._astar = NavmeshAStarAlgorithm()
        self._funnel = FunnelAlgorithm()

    @property
    def random_point(self):
        node = get_random_polygon(self.nodes)
        return get_random_point(node)

    def destroy(self):
        DeregisterPhysicsNode.invoke(self._bullet_node.node())

    @staticmethod
    def _create_bullet_nodepath(geom, geom_node, entity):
        bullet_node = BulletRigidBodyNode("NavmeshCollision")

        transform = geom_node.getTransform()
        mesh = BulletTriangleMesh()
        mesh.addGeom(geom, True, transform)

        shape = BulletTriangleMeshShape(mesh, dynamic=False)
        bullet_node.addShape(shape)

        mask = BitMask32()
        mask.set_word(CollisionGroups.navmesh)

        bullet_node.set_into_collide_mask(mask)

        # Associate with entity
        bullet_nodepath = base.render.attach_new_node(bullet_node)
        bullet_nodepath.set_python_tag("entity", entity)

        bullet_nodepath.hide()

        return bullet_nodepath

    @staticmethod
    def _create_kd_tree(nodes):
        node_positions = []

        vertex_positions_to_nodes = {}

        for node in nodes:
            for vertex_position in node.vertices:
                try:
                    nodes = vertex_positions_to_nodes[vertex_position]

                except KeyError:
                    nodes = vertex_positions_to_nodes[vertex_position] = []

                    # If it doesn't exist yet, add to node positions
                    bound_vector = BoundVector(vertex_position)
                    bound_vector.data = nodes
                    node_positions.append(bound_vector)

                nodes.append(node)

        return KDTree(node_positions, 2)

    def find_nearest_node(self, point):
        """Find the nearest A* node to a given point

        If the point is not inside of any A* node, the nearest node by vertex is selected

        :param point: point to test
        """
        nearest_kdnode = self.kd_tree.nn_search(point, 1)[1]
        nearest_vertex_position = nearest_kdnode.position
        nearest_vertex_nodes = nearest_vertex_position.data

        # First test if inside nodes
        for node in nearest_vertex_nodes:
            if point in node:
                return node

        # Else, fallback with closest by origin
        closest_distance_squared = 1e32
        closest_node = None

        for node in nearest_vertex_nodes:
            distance_squared = (node.position - nearest_vertex_position).length_squared
            if distance_squared < closest_distance_squared:
                closest_distance_squared = distance_squared
                closest_node = node

        return closest_node

    def find_path(self, from_point, to_point, from_node=None, to_node=None):
        # from_node=None
        # to_node=None

        if from_node is None:
            from_node = self.find_nearest_node(from_point)

        if to_node is None:
            to_node = self.find_nearest_node(to_point)

        nodes = self._astar.find_path(goal=to_node, start=from_node)
        points = self._funnel.find_path(source=from_point, destination=to_point, nodes=nodes)

        return NavigationPath(points=points, nodes=nodes)

    @classmethod
    def _parse_geom(cls, geom):
        primitive = geom.get_primitives()[0]
        vertex_data = geom.get_vertex_data()

        vertex_reader = GeomVertexReader(vertex_data, 'vertex')
        triangle_count = primitive.get_num_primitives()

        triangles = []
        vertex_positions = {}

        # Get triangles and vertex positions
        for triangle_index in range(triangle_count):
            start_index = primitive.get_primitive_start(triangle_index)
            end_index = primitive.get_primitive_end(triangle_index)

            vertex_indices = []
            for i in range(start_index, end_index):
                vertex_index = primitive.get_vertex(i)

                vertex_reader.set_row(vertex_index)
                vertex_position = Vector(vertex_reader.getData3f())

                vertex_positions[vertex_index] = vertex_position.freeze()
                vertex_indices.append(vertex_index)

            triangles.append(tuple(vertex_indices))

        triangles_to_neighbours = cls._build_neighbours(triangles)
        return cls._build_nodes(triangles_to_neighbours, vertex_positions)

    @staticmethod
    def _build_nodes(triangles_to_neighbours, vertex_positions):
        triangles_to_polygons = {triangle: PandaNavmeshNode([vertex_positions[i] for i in triangle])
                                 for triangle in triangles_to_neighbours}
        polygons = []

        for triangle, polygon in triangles_to_polygons.items():
            # Get neighbours
            for neighbour in triangles_to_neighbours[triangle]:
                # Add neighbour to neighbour list
                neighbour_polygon = triangles_to_polygons[neighbour]
                polygon.neighbours.add(neighbour_polygon)

            polygons.append(polygon)

        return polygons

    @staticmethod
    def _slice_triangles(vertices):
        triangles = []
        for i in range(0, len(vertices), 3):
            try:
                triangle = tuple(vertices[i: i + 3])

            except IndexError:
                break

            triangles.append(triangle)

        return triangles

    @staticmethod
    def _build_neighbours(triangles):
        triangle_sets = [set(t) for t in triangles]
        triangle_neighbours = {}

        for triangle, triangle_set in zip(triangles, triangle_sets):
            neighbours = [t for t, t_set in zip(triangles, triangle_sets) if len(t_set & triangle_set) == 2]
            triangle_neighbours[triangle] = neighbours

        return triangle_neighbours


@with_tag("camera")
class PandaCameraInterface(PandaComponent):

    def __init__(self, config_section, entity, nodepath):
        self._entity = entity
        self._nodepath = nodepath
        self._node = nodepath.node()

        self._display_region = self._get_display_region()
        self._node.showFrustum()

    @property
    def active(self):
        # Check if the active camera is this camera
        return self._display_region.get_camera() == self._nodepath

    def set_active(self):
        if self.active:
            return

        region = self._get_display_region()
        region.set_camera(self._nodepath)

    @staticmethod
    def _get_display_region():
        scene_root_node = base.render.node()

        for region in base.win.get_display_regions():
            camera = region.get_camera()
            nodes = camera.get_nodes()
            if not nodes:
                continue

            root = nodes[-1]
            if root == scene_root_node:
                return region

    @contextmanager
    def active_context(self):
        region = self._display_region
        active_camera = region.get_camera()

        region.set_camera(self._nodepath)
        yield
        region.set_camera(active_camera)

    def is_point_in_frustum(self, point):
        """Determine if a point resides in the camera frustum

        :param point: :py:class:`mathutils.Vector`
        :rtype: bool
        """
        camera = self._nodepath
        relative_point = camera.get_relative_point(base.render, point)
        return camera.is_in_view(relative_point)

    def is_sphere_in_frustum(self, point, radius):
        """Determine if a sphere resides in the camera frustum

        :param point: :py:class:`mathutils.Vector`
        :param radius: radius of sphere
        :rtype: bool
        """
        relative_point = self._nodepath.get_relative_point(base.render, point)
        bounds = BoundingSphere(relative_point, radius)
        return self._node.get_bounds().contains(bounds) in {BoundingSphere.IF_some, BoundingSphere.IF_all}

    def get_screen_direction(self, x=0.5, y=0.5):
        """Find direction along screen vector

        :param x: screen space x coordinate
        :param y: screen space y coordinate
        """
        mouse_pos = x, y
        from_point = Point3()
        to_point = Point3()

        self._node.get_lens().extrude(mouse_pos, from_point, to_point)
        relative_direction = to_point - from_point
        direction = base.render.get_relative_vector(self._nodepath, relative_direction)
        return Vector(direction)


@with_tag("Panda")
class PandaComponentLoader(ComponentLoader):

    def __init__(self, *component_tags):
        self.component_tags = component_tags
        self.component_classes = {tag: PandaComponent.find_subclass_for(tag) for tag in component_tags}

    @staticmethod
    def create_object(config_parser, entity):
        file_name = config_parser['model_name']

        if "bam" not in file_name:
            entity_data = ResourceManager[entity.__class__.type_name]
            model_path = path.join(entity_data.absolute_path, file_name)
            panda_filename = Filename.fromOsSpecific(model_path)

            obj = base.loader.loadModel(panda_filename)

        else:
            obj = entity.create_object()

        obj.reparentTo(base.render)

        return obj

    @classmethod
    def find_object(cls, config_parser):
        object_name = config_parser['model_name']
        node_path = base.render.find("*{}".format(object_name))
        return node_path

    # todo: don't use name, use some tag to indicate top level parent

    @classmethod
    def find_or_create_object(cls, entity, config_parser):
        if entity.is_static:
            return cls.find_object(config_parser)

        return cls.create_object(config_parser, entity)

    def load(self, entity, config_parser):
        nodepath = self.find_or_create_object(entity, config_parser)
        nodepath.set_python_tag("entity", entity)

        components = self._load_components(config_parser, entity, nodepath)

        def on_unloaded():
            nodepath.removeNode()

        result = ComponentLoaderResult(components)
        result.on_unloaded = on_unloaded

        return result
