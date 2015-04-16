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
from game_system.signals import CollisionSignal, UpdateCollidersSignal
from game_system.resources import ResourceManager

from .signals import RegisterPhysicsNode, DeregisterPhysicsNode

from panda3d.bullet import BulletRigidBodyNode
from panda3d.core import Filename, Vec3
from os import path
from functools import partial


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

    def destroy(self):
        for child in self._registered_nodes:
            DeregisterPhysicsNode.invoke(child)

    @property
    def world_linear_velocity(self):
        return Vector(self._node.getLinearVelocity())

    @world_linear_velocity.setter
    def world_linear_velocity(self, velocity):
        self._node.setLinearVelocity(tuple(velocity))

    @property
    def world_angular_velocity(self):
        return Vector(self._node.getAngularVelocity())

    @world_angular_velocity.setter
    def world_angular_velocity(self, angular):
        self._node.setAngularVelocity(tuple(angular))

    @property
    def local_linear_velocity(self):
        parent = self._nodepath.getParent()

        inverse_rotation = parent.getQuat()
        inverse_rotation.invertInPlace()

        velocity = self._node.getLinearVelocity()
        inverse_rotation.xform(velocity)

        return Vector(velocity)

    @local_linear_velocity.setter
    def local_linear_velocity(self, velocity):
        velocity_ = Vec3(*velocity)
        parent = self._nodepath.getParent()

        rotation = parent.getQuat()
        rotation.xform(velocity_)

        self._node.setLinearVelocity(velocity_)

    @property
    def local_angular_velocity(self):
        parent = self._nodepath.getParent()

        inverse_rotation = parent.getQuat()
        inverse_rotation.invertInPlace()

        angular = self._node.getAngularVelocity()
        inverse_rotation.xform(angular)

        return Vector(angular)

    @local_angular_velocity.setter
    def local_angular_velocity(self, angular):
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
        return Euler((p, r, h))

    @world_orientation.setter
    def world_orientation(self, orientation):
        p, r, h = orientation
        self._nodepath.setHpr(base.render, h, p, r)

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
        object_name = config_parser['model_name']

        entity_data = ResourceManager[entity.__class__.type_name]

        file_name = "{}".format(object_name)
        model_path = path.join(entity_data.absolute_path, file_name)
        panda_filename = Filename.fromOsSpecific(model_path)

        obj = base.loader.loadModel(panda_filename)
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
        obj = self.find_or_create_object(entity, config_parser)
        components = self._load_components(config_parser, entity, obj)
        return PandaComponentLoaderResult(components, obj)

    def unload(self, loader_result):
        for component in loader_result.components.values():
            component.destroy()

        root_nodepath = loader_result.root_nodepath
        root_nodepath.removeNode()


class PandaComponentLoaderResult(ComponentLoaderResult):

    def __init__(self, components, root_nodepath):
        self.root_nodepath = root_nodepath
        self.components = components

