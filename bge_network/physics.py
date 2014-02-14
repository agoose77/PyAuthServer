from .replicables import Actor, Pawn, Controller, Camera, Weapon, ReplicableInfo, PlayerController
from .enums import PhysicsType
from .signals import (PhysicsReplicatedSignal,
                     PhysicsTickSignal, PhysicsSingleUpdateSignal,
                     PhysicsRoleChangedSignal, MapLoadedSignal,
                     UpdateCollidersSignal, PhysicsCopyState,
                     PhysicsRewindSignal)
from .structs import RigidBodyState

from bge import logic
from collections import deque, defaultdict
from contextlib import contextmanager
from network import (WorldInfo, Netmodes, SignalListener,
                     ReplicableUnregisteredSignal, Replicable,
                     NetmodeSwitch, netmode_switch, TypeRegister,
                     FactoryDict, Roles)

__all__ = ["PhysicsSystem", "ServerPhysics", "ClientPhysics"]


class PhysicsSystem(NetmodeSwitch, SignalListener, metaclass=TypeRegister):

    def __init__(self, update_func, apply_func):
        super().__init__()

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._rewind_buffers = defaultdict(deque)
        self._rewind_length = 1 * WorldInfo.tick_rate

    @PhysicsRewindSignal.global_listener
    def rewind_to(self, target_tick):
        raise NotImplementedError

        rewind_buffers = self._rewind_buffers

        first_pawn, pawn_data = next(rewind_buffers.items().__iter__(), None)

        if first_pawn is None:
            return

        # Find rewinding
        for index, (from_tick, from_state) in enumerate(
                                                 reversed(pawn_data)):
            if from_tick <= target_tick:
                break
            target_tick = from_tick

        else:
            return

        # Apply rewinding
        if from_tick == target_tick:
            for pawn, buffer in rewind_buffers.items():
                try:
                    to_state = buffer[-(index + 1)][1]
                except IndexError:
                    continue

                rigid_state = RigidBodyState()
                rigid_state.from_tuple(to_state)

                self.interface_state(rigid_state, pawn)

        else:
            for pawn, buffer in rewind_buffers.items():
                delta_time = target_tick - from_timestamp
                progress = target_tick - from_timestamp
                factor = progress / delta_time
                try:
                    from_state = buffer[-(index + 1)][1]
                    to_state = buffer[-index][1]
                except IndexError:
                    continue

                state_f = RigidBodyState()
                state_f.from_tuple(from_state)
                state_t = RigidBodyState()
                state_t.from_tuple(to_state)
                state_f.lerp(state_t, factor)

                self.interface_state(state_f, pawn)

    def store_rewind_data(self):
        buffers = self._rewind_buffers
        tick = WorldInfo.tick

        for pawn in WorldInfo.subclass_of(Pawn):
            buffer = buffers[pawn]

            state = pawn.rigid_body_state.to_tuple()
            buffer.append((tick, state))

            if (tick - buffer[0][0]) > self._rewind_length:
                buffer.popleft()

    @PhysicsTickSignal.global_listener
    def update(self, scene, delta_time):
        """Send state with unset data so velocities"""
        """reflect results of behaviour"""
        for replicable in WorldInfo.subclass_of(Actor):
            self.interface_state(replicable,
                                 replicable.rigid_body_state)

        super().update(scene, delta_time)

        self.store_rewind_data()


@netmode_switch(Netmodes.client)
class ClientPhysics(PhysicsSystem):

    small_correction_squared = 3

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

