from network.replicable import ReplicableMetacls, Replicable


class EntityMetacls(ReplicableMetacls):

    def __new__(metacls, name, bases, namespace):
        namespace["components"] = components = {}

        # Inherit from parent classes
        for cls in reversed(bases):
            if not isinstance(cls, metacls):
                continue

            components.update(cls.components)

        for attr_name, value in namespace.items():
            if isinstance(value, GenericComponent):
                components[attr_name] = value

        return super().__new__(metacls, name, bases, namespace)


class EntityBuilderBase:

    component_classes = None

    def load_entity(self, entity):
        for component_name, component in entity.components.items():
            try:
                instance_component_cls = self.component_classes[component.__class__]
            except KeyError:
                raise RuntimeError("No component class is registered for ({}){}.{}"
                                   .format(component.__class__.__name__, entity.__class__.__name__, component_name))
            instance_component = instance_component_cls(entity, component)
            setattr(entity, component_name, instance_component)


    @classmethod
    def register_class(cls, generic_class, specific_class):
        cls.component_classes[generic_class] = specific_class


class GenericComponent:

    pass


class GraphicsComponent(GenericComponent):
    pass


class MeshComponent(GraphicsComponent):

    def __init__(self, mesh_name):
        self.mesh_name = mesh_name


class TransformComponent(GenericComponent):

    def __init__(self, position=(0, 0, 0), orientation=(0, 0, 0)):
        self.position = position
        self.orientation = orientation


class Entity(Replicable, metaclass=EntityMetacls):

    pass