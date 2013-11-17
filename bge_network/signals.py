from network import Signal


class CollisionSignal(Signal):
    pass


class SetMoveTarget(Signal):
    pass


class PhysicsReplicatedSignal(Signal):
    pass


class PhysicsSingleUpdateSignal(Signal):
    pass


class PhysicsSetSimulatedSignal(Signal):
    pass


class PhysicsUnsetSimulatedSignal(Signal):
    pass


class ActorDamagedSignal(Signal):
    pass


class ActorKilledSignal(Signal):
    pass


class PlayerInputSignal(Signal):
    pass


class PhysicsTickSignal(Signal):
    pass


class MapLoadedSignal(Signal):
    pass


class GameExitSignal(Signal):
    pass
