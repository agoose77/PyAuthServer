from .actors import Actor
from .enums import PhysicsType

from bge import logic
from collections import defaultdict
from functools import partial
from network import WorldInfo, Netmodes
from time import monotonic


class SimulationEntry:

    def __init__(self, actor, callback=None):
        self.callback = callback
        self.actor = actor

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


class PhysicsSystem:

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
        self._update_func = update_func
        self._apply_func = apply_func
        self._active_physics = [PhysicsType.dynamic, PhysicsType.rigid_body]

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
            this_actor.suspend_physics()

        self._update_func(delta_time)

        for this_actor in WorldInfo.subclass_of(Actor):
            if this_actor == actor:
                continue
            this_actor.restore_physics()

        self._apply_func()

    def restore_objects(self):
        pass

    def update(self, scene, delta_time):

        # Restore scheduled objects
        for actor in self._exempt_actors:
            try:
                actor.suspend_physics()
            except RuntimeError:
                print(actor, "was not removed from the exempt actors list")

        self._update_func(delta_time)

        # Restore scheduled objects
        for actor in self._exempt_actors:
            actor.restore_physics()

        self._apply_func()
        self.restore_objects()


class ServerPhysics(PhysicsSystem):

    def restore_objects(self):

        for actor in WorldInfo.subclass_of(Actor):
            state = actor.rigid_body_state

            # Can probably do this once then use muteable property
            state.position = actor.position.copy()
            state.velocity = actor.velocity.copy()
            state.rotation = actor.rotation.copy()
            state.angular = actor.angular.copy()


class ClientPhysics(PhysicsSystem):

    small_correction_squared = 1

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
