from game_system.configobj import ConfigObj


class Entity:

    interface_names = ()
    configuration_pattern = "{}.conf"


class EntityConfigurationManager:

    def __init__(self, resource_manager):
        self._resource_manager = resource_manager

    def configure_entity(self, entity):
        file_name = entity.__class__.configuration_pattern.format(entity.__class__.__name__)

        with self._resource_manager.open(file_name) as f:
            config_obj = ConfigObj(f)

        self._apply_configuration(config_obj, entity)

    def _apply_configuration(self, configuration, entity):
        raise NotImplementedError