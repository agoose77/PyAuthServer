from .replicables import Actor, Pawn, Controller, Camera, Weapon, ReplicableInfo
from .enums import PhysicsType
from .signals import (CollisionSignal, PhysicsReplicatedSignal,
                     PhysicsTickSignal, PhysicsSingleUpdateSignal,
                     PhysicsSetSimulatedSignal, PhysicsUnsetSimulatedSignal,
                     MapLoadedSignal, UpdateCollidersSignal)

from bge import logic, types
from collections import defaultdict
from functools import partial
from network import (WorldInfo, Netmodes, SignalListener,
                     ReplicableUnregisteredSignal, Replicable)
from time import monotonic


class PhysicsSystem(SignalListener):

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
        super().__init__()

        self._exempt_actors = []
        self._update_func = update_func
        self._apply_func = apply_func
        self._active_physics = [PhysicsType.dynamic, PhysicsType.rigid_body]

        self.register_signals()

    def on_conversion_error(self, lookup, err):
        print("Unable to convert {}: {}".format(lookup, err))

    def get_actor(self, lookup, name, type_of):
        if not name in lookup:
            return

        instance_id = lookup.get(name + "_id")

        try:
            name_cls = Replicable.from_type_name(lookup[name])
            assert issubclass(name_cls, type_of), ("Failed to find parent" \
                       " class type {} in requested instance".format(type_of))
            return name_cls(instance_id=instance_id)

        except (AssertionError, LookupError) as e:
            self.on_conversion_error(lookup, e)

    def setup_map_controller(self, pawn, obj):
        controller = self.get_actor(obj, "controller", Controller)
        camera = self.get_actor(obj, "camera", Camera)
        info = self.get_actor(obj, "info", ReplicableInfo)

        try:
            assert not None in (camera, controller, info), "Failed to find camera, controller and info"

        except AssertionError as e:
            self.on_conversion_error(obj, e)
            return

        controller.info = info
        controller.possess(pawn)
        controller.set_camera(camera)

        weapon = self.get_actor(obj, "weapon", Weapon)
        if weapon is None:
            return

        controller.setup_weapon(weapon)
        if pawn.weapon_attachment_class is not None:
            pawn.create_weapon_attachment(pawn.weapon_attachment_class)

    @MapLoadedSignal.global_listener
    def convert_map(self, target=None):
        scene = logic.getCurrentScene()

        found_actors = {}

        # Conversion step
        for obj in scene.objects:
            actor = self.get_actor(obj, "replicable", Actor)

            if actor is None:
                continue

            print("Loaded {}".format(actor))
            found_actors[obj] = actor

            actor.position = obj.worldPosition.copy()
            actor.rotation = obj.worldOrientation.to_euler()

            if isinstance(actor, Pawn):
                self.setup_map_controller(actor, obj)

        # Establish parent relationships
        for obj, actor in found_actors.items():
            if obj.parent in found_actors:
                actor.set_parent(found_actors[obj.parent])
            obj.endObject()

    @ReplicableUnregisteredSignal.global_listener
    def notify_unregistration(self, target):
        self.remove_exemption(target)

    @PhysicsUnsetSimulatedSignal.global_listener
    def add_exemption(self, target):
        if not target in self._exempt_actors:
            self._exempt_actors.append(target)

    @PhysicsSetSimulatedSignal.global_listener
    def remove_exemption(self, target):
        if target in self._exempt_actors:
            self._exempt_actors.remove(target)

    @PhysicsSingleUpdateSignal.global_listener
    def update_for(self, delta_time, target):
        if not target.physics in self._active_physics:
            return

        # Make a list of objects we touched
        modified_states = []
        for this_target in WorldInfo.subclass_of(Actor):
            if this_target == target:
                continue

            this_target.suspended = True
            modified_states.append(this_target)

        self._update_func(delta_time)

        # Restore suspended actors
        for this_target in modified_states:
            this_target.suspended = False

        self._apply_func()

    def update(self, scene, delta_time):

        # Restore scheduled objects
        for actor in self._exempt_actors:
            actor.suspended = True

        self._update_func(delta_time)

        # Restore scheduled objects
        for actor in self._exempt_actors:
            actor.suspended = False

        self._apply_func()

        UpdateCollidersSignal.invoke()


class ServerPhysics(PhysicsSystem):

    @PhysicsTickSignal.global_listener
    def update(self, scene, delta_time):
        super().update(scene, delta_time)

        for replicable in WorldInfo.subclass_of(Actor):
            state = replicable.rigid_body_state

            state.position[:] = replicable.position
            state.velocity[:] = replicable.velocity
            state.angular[:] = replicable.angular
            state.rotation[:] = replicable.rotation


class ClientPhysics(PhysicsSystem):

    small_correction_squared = 1

    @PhysicsTickSignal.global_listener
    def update(self, scene, delta_time):
        super().update(scene, delta_time)

    def get_actor(self, lookup, name, type_of):
        if not name + "_id" in lookup:
            return
        return super().get_actor(lookup, name, type_of)

    @PhysicsReplicatedSignal.global_listener
    def actor_replicated(self, target_physics, target):
        difference = target_physics.position - target.position

        small_correction = difference.length_squared < \
                            self.small_correction_squared

        if small_correction:
            target.position += difference * 0.2
            target.velocity = target_physics.velocity + difference * 0.8

        else:
            target.position = target_physics.position.copy()
            target.velocity = target_physics.velocity.copy()

        target.rotation = target_physics.rotation.copy()
        target.angular = target_physics.angular.copy()
