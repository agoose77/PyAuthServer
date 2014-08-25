from network.replicable import Replicable

from .configobj import ConfigObj
from .resources import ResourceManager
from .definitions import ComponentLoader


class Entity:

    component_tags = []
    definition_name = "definition.cfg"

    _definitions = {}

    def __init__(self, *args, **kwargs):
        self.load_components()

        super().__init__(*args, **kwargs)

    def load_components(self):
        self_class = self.__class__

        # Lazy load component loader
        try:
            component_loader = self_class._component_loader

        except AttributeError:
            component_loader = ComponentLoader(*self_class.component_tags)
            self_class._component_loader = component_loader

        class_name = self_class.__name__
        definitions = self_class._definitions

        # Lazy load definitions
        try:
            platform_definition = definitions[class_name]

        except KeyError:
            resources = ResourceManager[class_name]
            platform = ResourceManager.environment

            try:
                definition = resources[self_class.definition_name]

            except TypeError:
                raise FileNotFoundError("Could not find definition file for {}".format(class_name))

            full_path = ResourceManager.from_relative_path(definition)

            definition_sections = ConfigObj(full_path)
            platform_definition = definition_sections[platform]
            definitions[class_name] = platform_definition

        components = component_loader.load_components(self, platform_definition)

        # Load components
        for component_tag, component in components.items():
            setattr(self, component_tag, component)


class Actor(Entity, Replicable):

    component_tags = ("physics", "animation")


class Camera(Actor, Replicable):

    component_tags = ("physics", "animation", "camera")