from game_system.entity import MeshComponent, TransformComponent, AnimationComponent, EntityBuilderBase

from . import components


class EntityBuilder(EntityBuilderBase):
    component_classes = {}

    def __init__(self, bge_scene, empty_name="Empty"):
        self.entity_to_game_obj = {}

        self._empty_name = empty_name
        self._bge_scene = bge_scene

    def load_entity(self, entity):
        object_name = self._empty_name

        for component_name, component in entity.components.items():
            if isinstance(component, MeshComponent):
                object_name = component.mesh_name
                break

        existing_obj = self._bge_scene.objectsInactive[object_name]
        obj = self._bge_scene.addObject(object_name, object_name)

        # Prevent double scaling
        obj.worldTransform = existing_obj.worldTransform.inverted() * obj.worldTransform

        self.entity_to_game_obj[entity] = obj
        super().load_entity(entity)

    def unload_entity(self, entity):
        obj = self.entity_to_game_obj.pop(entity)
        super().unload_entity(entity)
        obj.endObject()

    def create_component(self, entity, class_component, component_cls):
        obj = self.entity_to_game_obj[entity]
        return component_cls(entity, obj, class_component)


EntityBuilder.register_class(TransformComponent, components.TransformComponent)
EntityBuilder.register_class(MeshComponent, components.MeshComponent)
EntityBuilder.register_class(AnimationComponent, components.AnimationComponent)
