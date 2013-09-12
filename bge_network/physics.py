from .actors import Actor
from .enums import PhysicsType

from bge import logic, types
from collections import defaultdict
from functools import partial
from network import WorldInfo, Netmodes, FactoryDict, InstanceNotifier
from time import monotonic


class CollisionStatus:
    """Handles collision for Actors"""
    def __init__(self, actor):

        if hasattr(types.KX_GameObject, "collisionCallbacks"):
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
            self._actor.on_collision(other, True)

    def not_colliding(self):
        # If we have a stored collision
        difference = self._old_colliders.difference(self._new_colliders)

        self._old_colliders = self._new_colliders
        self._new_colliders = set()

        if not difference:
            return

        for obj in difference:
            self._registered.remove(obj)
            self._actor.on_collision(obj, False)

    def register_callback(self, actor):
        actor.object.collisionCallbacks.append(self.is_colliding)


class SimulationEntry:

    def replicablet__(self, actor, callback=None):
        self.callback = callback
        self.replicable = actor

        self._duration = None
        self._func = None

    def set_func(self, func):
        self._func = func

    @property
    def duration(self):
        return self._duration

    @duration.setter
    def duration(self, length):
        self._duration = length

        if length:
            self._func(length)


class PhysicsSystem(InstanceNotifier):

    def __new__(cls, *args, **kwargs):
        """Constructor switch depending upon netmode"""
        if cls is PhysicsSystem:
            netmode = WorldInfo.netmode

            if netmode == Netmodes.server:
                return ServerPhysics.__new__(ServerPhysics, *args, **kwargs)

            elif netmode == Netmodes.client:
                return ClientPhysics.__new__(ClientPhysics, *args, **kwargs)
        else:
            return super().__new__(cls)

    def __init__(self, update_func, apply_func):
        self._exempt_actors = []
        self._listeners = {}
        self._update_func = update_func
        self._apply_func = apply_func
        self._active_physics = [PhysicsType.dynamic, PhysicsType.rigid_body]

        Actor.subscribe(self)

    def notify_unregistration(self, replicable):
        self.remove_listener(replicable)

    def add_exemption(self, actor):
        print("{} is exempt from default physics".format(actor))
        self._exempt_actors.append(actor)

    def remove_exemption(self, actor):
        self._exempt_actors.remove(actor)

    def update_for(self, actor, delta_time):
        if not actor.physics in self._active_physics:
            return

        for this_actor in WorldInfo.subclass_of(Actor):
            if this_actor == actor:
                continue
            # Callbacks freeze
            if actor in self._listeners:
                self._listeners[actor].receive_collisions = False

            this_actor.suspend_physics()

        self._update_func(delta_time)

        for this_actor in WorldInfo.subclass_of(Actor):
            if this_actor == actor:
                continue

            if actor in self._listeners:
                self._listeners[actor].receive_collisions = True

            this_actor.restore_physics()

        self._apply_func()

    def restore_objects(self):
        pass

    def update(self, scene, delta_time):

        # Restore scheduled objects
        for actor in self._exempt_actors:
            try:
                actor.suspend_physics()

                if actor in self._listeners:
                    self._listeners[actor].receive_collisions = False

            except RuntimeError:
                print(actor, "was not removed from the exempt actors list")

        self._update_func(delta_time)

        # Restore scheduled objects
        for actor in self._exempt_actors:

            if actor in self._listeners:
                self._listeners[actor].receive_collisions = True

            actor.restore_physics()

        self._apply_func()

    def needs_listener(self, replicable):
        return replicable.physics in self._active_physics and not \
                            replicable in self._listeners

    def create_listener(self, replicable):
        self._listeners[replicable] = CollisionStatus(replicable)

    def remove_listener(self, replicable):
        self._listeners.pop(replicable, None)


class ServerPhysics(PhysicsSystem):

    def update(self, scene, delta_time):
        super().update(scene, delta_time)

        for replicable in WorldInfo.subclass_of(Actor):
            state = replicable.rigid_body_state

            # Can probably do this once then use muteable property
            state.position = replicable.position.copy()
            state.velocity = replicable.velocity.copy()
            state.rotation = replicable.rotation.copy()
            state.angular = replicable.angular.copy()

            # If we need to make a callback instance
            if self.needs_listener(replicable):
                self.create_listener(replicable)


class ClientPhysics(PhysicsSystem):

    small_correction_squared = 1

    def update(self, scene, delta_time):
        super().update(scene, delta_time)

        for replicable in WorldInfo.subclass_of(Actor):

            # If we need to make a callback instance
            if self.needs_listener(replicable):
                self.create_listener(replicable)

    def actor_replicated(self, actor, actor_physics):
        difference = actor_physics.position - actor.position

        small_correction = difference.length_squared < \
                            self.small_correction_squared

        if small_correction:
            actor.position += difference * 0.2
            actor.velocity = actor_physics.velocity + difference * 0.8

        else:
            actor.position = actor_physics.position.copy()
            actor.velocity = actor_physics.velocity.copy()

        actor.rotation = actor_physics.rotation.copy()
        actor.angular = actor_physics.angular.copy()
