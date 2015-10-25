from game_system.entity import MeshComponent, TransformComponent, AnimationComponent, PhysicsComponent, \
    CameraComponent, EntityBuilderBase

from . import instance_components

from panda3d.core import NodePath


class EntityBuilder(EntityBuilderBase):
    component_classes = {}

    def __init__(self, root_nodepath):
        self.entity_to_nodepath = {}

        self._root_nodepath = root_nodepath

    def load_entity(self, entity):
        nodepath = NodePath(entity.__class__.__name__)

        # Create components
        super().load_entity(entity)

        # Ask for root nodepath
        components = set()

        for name in entity.components:
            component = getattr(entity, name)
            components.add(component)

            nodepath = component.update_root_nodepath(nodepath)

        # Set root nodepath
        for component in components:
            component.set_root_nodepath(nodepath)

        self.entity_to_nodepath[entity] = nodepath
        nodepath.reparent_to(self._root_nodepath)

    def unload_entity(self, entity):
        nodepath = self.entity_to_nodepath.pop(entity)
        super().unload_entity(entity)

        nodepath.remove_node()

    def create_component(self, entity, class_component, component_cls):
        return component_cls(entity, class_component)


EntityBuilder.register_class(TransformComponent, instance_components.TransformInstanceComponent)
EntityBuilder.register_class(MeshComponent, instance_components.MeshInstanceComponent)
EntityBuilder.register_class(AnimationComponent, instance_components.AnimationInstanceComponent)
EntityBuilder.register_class(PhysicsComponent, instance_components.PhysicsInstanceComponent)
