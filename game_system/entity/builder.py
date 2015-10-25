from network.replicable import ReplicableMetacls

from .class_components import ClassComponent


class EntityMetacls(ReplicableMetacls):

    def __new__(metacls, name, bases, namespace):
        namespace["components"] = components = {}

        # Inherit from parent classes
        for cls in reversed(bases):
            if not isinstance(cls, metacls):
                continue

            components.update(cls.components)

        for attr_name, value in namespace.items():
            if isinstance(value, ClassComponent):
                components[attr_name] = value

        return super().__new__(metacls, name, bases, namespace)


class EntityBuilderBase:

    component_classes = None

    def create_component(self, entity, class_component, component_cls):
        raise NotImplementedError()

    def load_entity(self, entity):
        for component_name, component in entity.components.items():
            try:
                instance_component_cls = self.component_classes[component.__class__]
            except KeyError:
                raise RuntimeError("No component class is registered for ({}){}.{}"
                                   .format(component.__class__.__name__, entity.__class__.__name__, component_name))
            instance_component = self.create_component(entity, component, instance_component_cls)

            setattr(entity, component_name, instance_component)

    def unload_entity(self, entity):
        for component_name, component in entity.components.items():
            instance_component = getattr(entity, component_name)
            instance_component.on_destroyed()

            delattr(entity, component_name)

    @classmethod
    def register_class(cls, generic_class, specific_class):
        cls.component_classes[generic_class] = specific_class

