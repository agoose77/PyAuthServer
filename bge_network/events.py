from network import Event


class CollisionEvent(Event):
    pass


class PhysicsReplicatedEvent(Event):
    pass


class PhysicsSingleUpdate(Event):
    pass


class PhysicsSetSimulated(Event):
    pass


class PhysicsUnsetSimulated(Event):
    pass


class ActorDamagedEvent(Event):
    pass


class PlayerInputEvent(Event):
    pass


class PhysicsTickEvent(Event):
    pass
