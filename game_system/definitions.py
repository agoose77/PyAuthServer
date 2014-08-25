from configparser import ConfigParser
from .resources import ResourceManager
from network.tagged_delegate import TaggedDelegateMeta


class EnvironmentDefinitionMeta(TaggedDelegateMeta):

    @staticmethod
    def get_current_tag():
        return ResourceManager.environment


class ActorDefinition(EnvironmentDefinitionMeta):
    subclasses = {}

    pass


class Actor:

    def load_components(self):
        class_name = self.__class__.__name__
        resources = ResourceManager[class_name]
        platform = ResourceManager.environment
        definition = resources["definition.cfg"]
        definition_sections = ConfigParser()
        full_path = ResourceManager.from_relative_path(definition)
        definition_sections.read(full_path)

        platform_definition = definition_sections[platform]
        actor_definition = ActorDefinition(platform_definition)

        self.physics = actor_definition.physics
        self.animation = actor_definition.animation
