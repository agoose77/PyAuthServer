__all__ = "ClassComponent", "GraphicsComponent", "MeshComponent", "TransformComponent", "PhysicsComponent", \
    "AnimationComponent", "CameraComponent"


class ClassComponent:
    pass


# Class components
class GraphicsComponent(ClassComponent):
    pass


class MeshComponent(GraphicsComponent):

    def __init__(self, mesh_name):
        self.mesh_name = mesh_name


class TransformComponent(ClassComponent):

    def __init__(self, position=(0, 0, 0), orientation=(0, 0, 0)):
        self.position = position
        self.orientation = orientation


class AnimationComponent(ClassComponent):
    pass


class CameraComponent(ClassComponent):
    pass


class PhysicsComponent(ClassComponent):
    pass