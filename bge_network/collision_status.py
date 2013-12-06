from signals import CollisionSignal, ClearCollisionsSignal


class CollisionStatus:
    """Handles collision for Actors"""
    def __init__(self, actor):

        self.register_callback(actor)

        self._new_colliders = set()
        self._old_colliders = set()
        self._registered = set()
        self._actor = actor

        self.receive_collisions = True

    @property
    def colliding(self):
        return bool(self._registered)

    def is_colliding(self, other, data):
        if not self.receive_collisions:
            return

        # If we haven't already stored the collision
        self._new_colliders.add(other)

        if not other in self._registered:
            self._registered.add(other)
            CollisionSignal.invoke(other, True, target=self._actor)

    @ClearCollisionsSignal.global_listener
    def not_colliding(self):
        if not self.receive_collisions:
            return

        # If we have a stored collision
        difference = self._old_colliders.difference(self._new_colliders)

        self._old_colliders = self._new_colliders
        self._new_colliders = set()

        if not difference:
            return

        for obj in difference:
            self._registered.remove(obj)

            CollisionSignal.invoke(obj, False, target=self._actor)

    def register_callback(self, actor):
        callbacks = actor.object.collisionCallbacks

        if not self.is_colliding in callbacks:
            callbacks.append(self.is_colliding)
