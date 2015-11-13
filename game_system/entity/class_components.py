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

    def __init__(self, position=None, orientation=None):
        self.position = position
        self.orientation = orientation


class AnimationComponent(ClassComponent):
    pass


class CameraComponent(ClassComponent):
    pass


class PhysicsComponent(ClassComponent):

    def __init__(self, mesh_name=None, mass=None, collision_group=0, collision_mask=0):
        self.mesh_name = mesh_name
        self.mass = mass
        self.collision_group = collision_group
        self.collision_mask = collision_mask