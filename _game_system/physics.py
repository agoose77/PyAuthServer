from collections import namedtuple

RayTestResult = namedtuple("RayTestResult", "position normal entity distance")
CollisionContact = namedtuple("CollisionContact", "position normal impulse")


class LazyCollisionResult:
    """Collision result container

    Lazily evaluate contact points on request
    """
    __slots__ = ("entity", "state", "_contacts_getter", "_contacts")

    def __init__(self, entity, state, contacts_getter):
        self.entity = entity
        self.state = state

        self._contacts_getter = contacts_getter
        self._contacts = None

    @property
    def contacts(self):
        contacts = self._contacts

        if contacts is None:
            contacts = self._contacts = self._contacts_getter()

        return contacts
