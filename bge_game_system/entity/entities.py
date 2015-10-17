from game_system.entity import MeshComponent, TransformComponent, AnimationComponent, EntityBuilderBase

from . import components


class EntityBuilder(EntityBuilderBase):
    component_classes = {}


EntityBuilder.register_class(TransformComponent, components.TransformComponent)
EntityBuilder.register_class(MeshComponent, components.MeshComponent)
EntityBuilder.register_class(AnimationComponent, components.AnimationComponent)