__all__ = "TransformComponent", "MeshComponent", "AnimationComponent"


class TransformComponent:

    def __init__(self, entity, component):
        print("Transform", component)


class MeshComponent:

    def __init__(self, entity, component):
        print("Mesh", component)


class AnimationComponent:

    def __init__(self, entity, component):
        print("Animation", component)