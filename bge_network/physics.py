from .replicables import Actor, Pawn, Controller, Camera, Weapon, ReplicableInfo
from .enums import PhysicsType
from .signals import (PhysicsReplicatedSignal,
                     PhysicsTickSignal, PhysicsSingleUpdateSignal,
                     PhysicsSetSimulatedSignal, PhysicsUnsetSimulatedSignal,
                     MapLoadedSignal, UpdateCollidersSignal, PhysicsCopyState)
from .structs import RigidBodyState

from bge import logic
from collections import deque, defaultdict
from mathutils import Vector
from contextlib import contextmanager
from network import (WorldInfo, Netmodes, SignalListener,
                     ReplicableUnregisteredSignal, Replicable,
                     NetmodeSwitch, netmode_switch, TypeRegister,
                     FactoryDict)

__all__ = ["EPICInterpolator", "PhysicsSystem", "ServerPhysics", "ClientPhysics"]


class EPICInterpolator:

    def __init__(self, actor):
        self.actor = actor

        self._last_time = None
        self._update_time = 1 / 25

    def add_sample(self, physics):
        position = self.actor.position
        timestamp = WorldInfo.elapsed

        self._last_time = timestamp#packet_timestamp

        aim_timestamp = timestamp + self._update_time
        delta_time = self._update_time #aim_timestamp - packet_timestamp
        # Where we intend to be in the future
        aim_position = physics.position + physics.velocity * delta_time

        if (abs(aim_timestamp - timestamp) < 0.001):
            velocity = physics.velocity

        else:
           # delta_time = 1.0 / (aim_timestamp - timestamp)
            velocity = (aim_position - position) * self._update_time

        new_state = RigidBodyState()
        new_state.position = position
        new_state.velocity = velocity
        new_state.rotation = physics.rotation
        new_state.angular = physics.angular
        new_state.collision_group = self.actor.collision_group
        new_state.collision_mask = self.actor.collision_mask 
        return new_state


class PhysicsSystem(NetmodeSwitch, SignalListener, metaclass=TypeRegister):

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

    @contextmanager
    def protect_exemptions(self, exemptions):
        # Suspend exempted objects
        for actor in exemptions:
            actor.suspended = True
        yield
        # Restore scheduled objects
        for actor in exemptions:
            actor.suspended = False

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

        # Make a list of actors which aren't us
        other_actors = [a for a in WorldInfo.subclass_of(Actor) if a != target]

        with self.protect_exemptions(other_actors):
            self._update_func(delta_time)

        self._apply_func()

    @PhysicsTickSignal.global_listener
    def update(self, scene, delta_time):
        # Restore scheduled objects
        with self.protect_exemptions(self._exempt_actors):
            self._update_func(delta_time)

        self._apply_func()

        UpdateCollidersSignal.invoke()

    @PhysicsCopyState.global_listener
    def interface_state(self, a, b):
        b.position = a.position.copy()
        b.velocity = a.velocity.copy()
        b.angular = a.angular.copy()
        b.rotation = a.rotation.copy()
        b.collision_group = a.collision_group
        b.collision_mask = a.collision_mask


@netmode_switch(Netmodes.server)
class ServerPhysics(PhysicsSystem):

    @PhysicsTickSignal.global_listener
    def update(self, scene, delta_time):
        super().update(scene, delta_time)

        for replicable in WorldInfo.subclass_of(Actor):
            state = replicable.rigid_body_state
            self.interface_state(replicable, state)


@netmode_switch(Netmodes.client)
class ClientPhysics(PhysicsSystem):

    small_correction_squared = 3

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.extrapolators = FactoryDict(EPICInterpolator)

    @ReplicableUnregisteredSignal.global_listener
    def notify_unregistration(self, target):
        super().notify_unregistration(target)

        if target in self.extrapolators:
            self.extrapolators.pop(target)

    def get_actor(self, lookup, name, type_of):
        if not name + "_id" in lookup:
            return
        return super().get_actor(lookup, name, type_of)

    @PhysicsReplicatedSignal.global_listener
    def actor_replicated(self, target_physics, target):
        difference = target_physics.position - target.position

        target.rotation = target_physics.rotation
        small_correction = difference.length_squared < \
                            self.small_correction_squared

        if small_correction:
            target.position += difference * 0.3
            target.velocity = target_physics.velocity# + difference

        else:
            target.position = target_physics.position
            target.velocity = target_physics.velocity

        target.angular = target_physics.angular
        target.collision_group = target_physics.collision_group
        target.collision_mask = target_physics.collision_mask

