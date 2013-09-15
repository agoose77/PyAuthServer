from .registers import Event, CachedEvent


class ReplicableRegisteredEvent(CachedEvent):
    pass


class ReplicableUnregisteredEvent(Event):
    pass


class ReplicableInstantiatedEvent(Event):
    pass
