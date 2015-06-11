from collections import namedtuple
from contextlib import contextmanager

from network.decorators import with_tag
from network.signals import SignalListener
from network.tagged_delegate import FindByTag
from network.logger import logger

from game_system.animation import Animation
from game_system.coordinates import Euler, Vector
from game_system.definitions import ComponentLoader, ComponentLoaderResult
from game_system.enums import AnimationMode, AnimationBlend, Axis, CollisionState, PhysicsType
from game_system.level_manager import LevelManager
from game_system.physics import CollisionResult, CollisionContact, RayTestResult
from game_system.signals import CollisionSignal, UpdateCollidersSignal
from game_system.resources import ResourceManager

from .signals import RegisterPhysicsNode, DeregisterPhysicsNode

from panda3d.bullet import BulletRigidBodyNode
from panda3d.core import Filename, Vec3
from os import path
from math import radians, degrees


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

        self._level_manager = LevelManager()
        self._level_manager.on_enter = self._on_enter_collision
        self._level_manager.on_exit = self._on_exit_collision

        # Setup callbacks
        self._nodepath.set_python_tag("on_contact_added", lambda n, c: self._level_manager.add(n, c))
        self._nodepath.set_python_tag("on_contact_removed", self._level_manager.remove)
        self._nodepath.set_python_tag("physics_component", self)

        self._node.notify_collisions(True)
        self._node.set_deactivation_enabled(False)

        self._suspended_mass = None

    @staticmethod
    def entity_from_nodepath(nodepath):
        if not nodepath.has_python_tag("physics_component"):
            return None

        component = nodepath.get_python_tag("physics_component")
        return component._entity

    def _on_enter_collision(self, other, contacts):
        hit_entity = self.entity_from_nodepath(other)

        result = CollisionResult(hit_entity, CollisionState.started, contacts)
        CollisionSignal.invoke(result, target=self._entity)

    def _on_exit_collision(self, other):
        hit_entity = self.entity_from_nodepath(other)

        result = CollisionResult(hit_entity, CollisionState.ended, None)
        CollisionSignal.invoke(result, target=self._entity)

    def destroy(self):
        for child in self._registered_nodes:
            DeregisterPhysicsNode.invoke(child)

    def ray_test(self, target, source=None, distance=0.0):
        """Perform a ray trace to a target

        :param target: target to trace towards
        :param source: optional origin of trace, otherwise object position
        :param distance: distance to use instead of vector length
        :rtype: :py:class:`game_system.physics.RayTestResult`
        """
        if source is None:
            source = Vector(self._nodepath.getPos(base.render))

        if distance:
            direction = target - source
            direction.length = distance

        world = self._node.get_python_tag("world")

        result = world.rayTestAll(tuple(source), tuple(target))
        for result in result.get_hits():
            hit_node = result.get_node()

            if hit_node is not self._node:
                hit_position = Vector(result.get_hit_pos())
                hit_entity = self.entity_from_nodepath(hit_node)
                hit_distance = (hit_position - source).length
                hit_normal = Vector(result.get_hit_normal())

                return RayTestResult(hit_position, hit_normal, hit_entity, hit_distance)

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

        current_parent.children.remove(self._nodepath)

        if parent is None:
            self._nodepath.wrtReparentTo(base.render)
            return

        if not isinstance(parent, PandaParentableBase):
            raise TypeError("Invalid parent type {}".format(parent.__class__.__name__))

        self._game_object.wrtReparentTo(parent._nodepath)

        parent.children.add(self._nodepath)
        self._parent = parent

    def create_sockets(self, nodepath):
        sockets = set()
        for child_nodepath in nodepath.find_all_matches("**/=socket"):
            socket_name = child_nodepath.get_python_tag("socket")
            socket = PandaSocket(socket_name, self, nodepath)
            sockets.add(socket)

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
        rotation.xform(direction)

        return Vector(direction)


@with_tag("Panda")
class PandaComponentLoader(ComponentLoader):

    def __init__(self, *component_tags):
        self.component_tags = component_tags
        self.component_classes = {tag: PandaComponent.find_subclass_for(tag) for tag in component_tags}

    @staticmethod
    def create_object(config_parser, entity):
        file_name = config_parser['model_name']
        print("SPAWN", entity)
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
        components = self._load_components(config_parser, entity, nodepath)

        def on_unloaded():
            nodepath.removeNode()

        result = ComponentLoaderResult(components)
        result.on_unloaded = on_unloaded

        return result

