class ITransformInterface:

    position = None
    rotation = None
    parent = None


class IPhysicsComponent:

    velocity = None
    angular = None
    collision_group = None
    collision_mask = None