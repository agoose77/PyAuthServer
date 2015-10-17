__all__ = "ClassComponent", "GraphicsComponent", "MeshComponent", "TransformComponent"


class ClassComponent:

    pass


class InstanceComponent:

    def on_unloaded(self):
        pass


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