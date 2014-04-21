from network.decorators import netmode_switch
from network.enums import Netmodes, Roles
from network.netmode_switch import NetmodeSwitch
from network.replicable import Replicable
from network.signals import SignalListener
from network.structures import FactoryDict
from network.type_register import TypeRegister
from network.world_info import WorldInfo

from bge import logic
from collections import deque
from contextlib import contextmanager

from .actors import Actor, Camera, Pawn
from .controllers import Controller
from .weapons import Weapon
from .replication_infos import ReplicationInfo

from .enums import PhysicsType
from .signals import *
from .structs import RigidBodyState


__all__ = ["PhysicsSystem", "ServerPhysics", "ClientPhysics"]


class PhysicsSystem(NetmodeSwitch, SignalListener, metaclass=TypeRegister):
    subclasses = {}

    def __init__(self, update_func, apply_func):
        super().__init__()

        self._update_func = update_func
        self._apply_func = apply_func
        self._active_physics = [PhysicsType.dynamic, PhysicsType.rigid_body]

    def on_conversion_error(self, lookup, err):
        print("Unable to convert {}: {}".format(lookup, err))

    def get_actor(self, lookup, name, type_of):
        '''Create an Actor instance from a BGE proxy object

        :param lookup: BGE proxy object
        :param name: Name of Actor class
        :param type_of: Required subclass that the Actor must inherit from'''
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

    def create_pawn_controller(self, pawn, obj):
        '''Setup a controller for given pawn object

        :param pawn: Pawn object
        :param obj: BGE proxy object'''
        controller = self.get_actor(obj, "controller", Controller)
        camera = self.get_actor(obj, "camera", Camera)
        info = self.get_actor(obj, "info", ReplicationInfo)

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

        controller.set_weapon(weapon)
        if pawn.weapon_attachment_class is not None:
            pawn.create_weapon_attachment(pawn.weapon_attachment_class)

    @contextmanager
    def protect_exemptions(self, exemptions):
        '''Suspend and restore state of exempted actors around an operation

        :param exemptions: Iterable of exempt Actor instances'''
        # Suspend exempted objects
        skip_updates = set()
        for actor in exemptions:
            if actor.suspended:
                skip_updates.add(actor)
                continue
            actor.suspended = True

        yield

        # Restore scheduled objects
        for actor in exemptions:
            if actor in skip_updates:
                continue
            actor.suspended = False

    @MapLoadedSignal.global_listener
    def convert_map(self, target=None):
        '''Listener for MapLoadedSignal
        Attempts to create network entities from BGE proxies'''
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
                self.create_pawn_controller(actor, obj)

        # Establish parent relationships
        for obj, actor in found_actors.items():
            if obj.parent in found_actors:
                actor.set_parent(found_actors[obj.parent])
            obj.endObject()

    @PhysicsSingleUpdateSignal.global_listener
    def update_for(self, delta_time, target):
        '''Listener for PhysicsSingleUpdateSignal
        Attempts to update physics simulation for single actor

        :param delta_time: Time to progress simulation
        :param target: Actor instance to update state'''
        if not target.physics in self._active_physics:
            return

        # Make a list of actors which aren't us
        other_actors = [a for a in WorldInfo.subclass_of(Actor)
                        if a != target and a]

        with self.protect_exemptions(other_actors):
            self._update_func(delta_time)
        self._apply_func()

    @PhysicsTickSignal.global_listener
    def update(self, scene, delta_time):
        '''Listener for PhysicsTickSignal
        Updates Physics simulation for entire world

        :param scene: BGE scene reference
        :param delta_time: Time to progress simulation'''
        self._update_func(delta_time)
        self._apply_func()

        UpdateCollidersSignal.invoke()

    @PhysicsCopyState.global_listener
    def interface_state(self, source_state, target_state):
        '''Copy state information from source to target

        :param source_state: State to copy from
        :param target_state: State to copy to'''
        target_state.position = source_state.position.copy()
        target_state.velocity = source_state.velocity.copy()
        target_state.angular = source_state.angular.copy()
        target_state.rotation = source_state.rotation.copy()
        target_state.collision_group = source_state.collision_group
        target_state.collision_mask = source_state.collision_mask


@netmode_switch(Netmodes.server)
class ServerPhysics(PhysicsSystem):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._rewind_buffers = {}
        self._rewind_keys = deque()
        self._rewind_length = 1 * WorldInfo.tick_rate

    @PhysicsRewindSignal.global_listener
    def rewind_to(self, target_tick=None):
        try:
            if target_tick is None:
                target_tick = self._rewind_keys[-1]
            tick_buffer = self._rewind_buffers[target_tick]

        except (IndexError, KeyError) as err:
            raise ValueError("Could not rewind to tick {}"
                             .format(target_tick)) from err

        # Apply rewinding
        for pawn, state in tick_buffer.items():
            rigid_state = RigidBodyState.from_tuple(state)

            self.interface_state(rigid_state, pawn)

    def store_rewind_data(self):
        tick = WorldInfo.tick

        # Store data
        self._rewind_buffers[tick] = {p: p.rigid_body_state.to_tuple()
                                      for p in WorldInfo.subclass_of(Pawn)}

        self._rewind_keys.append(tick)

        # Cap rewind length
        if (tick - self._rewind_keys[0]) > self._rewind_length:
            self._rewind_buffers.pop(self._rewind_keys[0])
            self._rewind_keys.popleft()

    @PhysicsTickSignal.global_listener
    def update(self, scene, delta_time):
        """Listener for PhysicsTickSignal
        Copy physics state to network variable for Actor instances"""

        for replicable in WorldInfo.subclass_of(Actor):
            assert replicable.registered
            self.interface_state(replicable,
                                 replicable.rigid_body_state)
        self.store_rewind_data()

        super().update(scene, delta_time)


@netmode_switch(Netmodes.client)
class ClientPhysics(PhysicsSystem):

    small_correction_squared = 3

    def get_actor(self, lookup, name, type_of):
        if not name + "_id" in lookup:
            return

        return super().get_actor(lookup, name, type_of)

    @PhysicsReplicatedSignal.global_listener
    def actor_replicated(self, target_physics, target):
        '''Listener for PhysicsReplicatedSignal
        Callback for physics state replication.
        Applies physics struct data to physics state.

        :param target_physics: Physics struct of target
        :param target: Actor instance'''

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

