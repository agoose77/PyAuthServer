from .resources import ResourceManager
from network.tagged_delegate import DelegateByTag


class EnvironmentDefinitionByTag(DelegateByTag):

    @staticmethod
    def get_current_tag():
        return ResourceManager.environment


class ComponentLoader(EnvironmentDefinitionByTag):

    subclasses = {}

    def _load_components(self, config_obj, *args, **kwargs):
        # Load all components
        components = {}

        for tag, component_cls in self.component_classes.items():
            config_data = config_obj.get(tag)
            component = component_cls(config_data, *args, **kwargs)
            components[tag] = component

        return components
