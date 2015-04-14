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

from panda3d.core import Filename
from os import path
from functools import partial


class PandaComponent(FindByTag):
    """Base class for Panda component"""

    subclasses = {}

    def destroy(self):
        """Destroy component"""
        pass


@with_tag("physics")
class T(PandaComponent):
    def __init__(self,a,c,d):
        pass

@with_tag("transform")
class PandaTransformInterface(PandaComponent, SignalListener):
    """Transform implementation for Panda entity"""

    def __init__(self, config_section, entity, obj):
        self._game_object = obj
        self._entity = entity

        self.parent = None
        self.children = set()

        self.register_signals()

    @property
    def world_position(self):
        return Vector(self._game_object.getPos(base.render))

    @world_position.setter
    def world_position(self, position):
        self._game_object.setPos(base.render, *position)

    @property
    def world_orientation(self):
        h, p, r = self._game_object.getHpr(base.render)
        return Euler((p, r, h))

    @world_orientation.setter
    def world_orientation(self, orientation):
        p, r, h = orientation
        self._game_object.setHpr(base.render, h, p, r)


@with_tag("Panda")
class PandaComponentLoader(ComponentLoader):

    def __init__(self, *component_tags):
        self.component_tags = component_tags
        self.component_classes = {tag: PandaComponent.find_subclass_for(tag) for tag in component_tags}

    @staticmethod
    def create_object(config_parser, entity):
        object_name = config_parser['egg_name']

        entity_data = ResourceManager[entity.__class__.type_name]

        file_name = "{}.egg".format(object_name)
        model_path = path.join(entity_data.absolute_path, file_name)
        panda_filename = Filename.fromOsSpecific(model_path)

        obj = base.loader.loadModel(panda_filename)
        obj.reparentTo(base.render)

        return obj

    @classmethod
    def find_object(cls, config_parser):
        object_name = config_parser['egg_name']
        node_path = base.render.find("*{}".format(object_name))
        return node_path

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

        game_object = loader_result.game_object
        game_object.removeNode()


class PandaComponentLoaderResult(ComponentLoaderResult):

    def __init__(self, components, obj):
        self.game_object = obj
        self.components = components

