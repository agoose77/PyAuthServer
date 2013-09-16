from .registers import Event, CachedEvent


class ReplicableRegisteredEvent(CachedEvent):
    pass


class ReplicationNotifyEvent(Event):
    pass


class ReplicableUnregisteredEvent(Event):
    pass


class UpdateEvent(Event):
    pass
