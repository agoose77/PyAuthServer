"""
The environment specified by ResourceManager.environment is used to select the appropriate ComponentLoader for the
current game engine

Each component that belongs to this definition can be selected by a tag i.e "physics" and these are specified in
the appropriate base classes for cameras, pawns etc, by instantiating a loader with the tags as arguments

class Pawn:
    component_loader = ComponentLoader("physics", "animation")

Each component is provided a configuration section which pertains to the section within a config file

[BGE]
    [physics]
        velocity = 1.0
        range = 2.0

This file is only used to load platform-specific data (like mesh names)

"""

from .tagged_delegate import EnvironmentDefinitionByTag


class ComponentLoader(EnvironmentDefinitionByTag):
    """Abstract component loader class"""

    subclasses = {}

    def _load_components(self, config_obj, *args, **kwargs):
        # Load all components
        components = {}

        for tag, component_cls in self.component_classes.items():
            config_data = config_obj.get(tag)
            component = component_cls(config_data, *args, **kwargs)
            components[tag] = component

        return components

    def load(self, entity, configuration):
        """Load components for given entity with configuration file

        :param entity: entity to load components
        :param configuration: configuration dictionary
        """
        raise NotImplementedError()


class ComponentLoaderResult:
    """Container for loaded components from :py:class:`game_system.definitions.ComponentLoader`"""

    def __init__(self, components):
        self.components = components

    def on_unloaded(self):
        """Callback on unloaded"""

    def unload(self):
        """Unload loaded components from ComponentLoader"""
        for component in self.components.values():
            component.destroy()

        self.on_unloaded()