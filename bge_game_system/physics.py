from collections import defaultdict
from contextlib import contextmanager
from operator import itemgetter

from network.decorators import with_tag
from network.enums import Netmodes, Roles
from network.logger import logger
from network.tagged_delegate import DelegateByNetmode
from network.replicable import Replicable
from network.signals import SignalListener, ReplicableUnregisteredSignal
from network.type_register import TypeRegister
from network.world_info import WorldInfo

from bge_game_system.actors import Actor, Camera, Pawn

from game_system.controllers import ControllerBase
from game_system.jitter_buffer import JitterBuffer
from game_system.weapons import Weapon
from game_system.replication_infos import ReplicationInfo
from game_system.enums import PhysicsType
from game_system.signals import *

from bge import logic
from mathutils import Vector


__all__ = ["PhysicsSystem", "ServerPhysics", "ClientPhysics", "EPICExtrapolator"]


class PhysicsSystem(DelegateByNetmode, SignalListener):
    subclasses = {}

    def __init__(self, update_func, apply_func):
        self.register_signals()

        self._update_func = update_func
        self._apply_func = apply_func
        self._active_physics = [PhysicsType.dynamic, PhysicsType.rigid_body]

    def on_conversion_error(self, lookup, err):
        print("Unable to convert {}: {}".format(lookup, err))

    def spawn_actor(self, lookup, name, type_of):
        """Create an Actor instance from a BGE proxy object

        :param lookup: BGE proxy object
        :param name: Name of Actor class
        :param type_of: Required subclass that the Actor must inherit from"""
        if not name in lookup:
            return

        instance_id = lookup.get(name + "_id")

        try:
            name_cls = Replicable.from_type_name(lookup[name])
            assert issubclass(name_cls, type_of), ("Failed to find parent class type {} in requested instance"
                                                   .format(type_of))
            try:
                return name_cls(instance_id=instance_id)

            except Exception:
                logger.exception("Couldn't spawn {} replicable".format(name))
                return

        except (AssertionError, LookupError) as e:
            self.on_conversion_error(lookup, e)

    def create_pawn_controller(self, pawn, obj):
        """Setup a controller for given pawn object

        :param pawn: Pawn object
        :param obj: BGE proxy object"""
        controller = self.spawn_actor(obj, "controller", ControllerBase)
        camera = self.spawn_actor(obj, "camera", Camera)
        info = self.spawn_actor(obj, "info", ReplicationInfo)

        try:
            assert not None in (camera, controller, info), "Failed to find camera, controller and info"

        except AssertionError as e:
            self.on_conversion_error(obj, e)
            return

        controller.info = info
        controller.possess(pawn)
        controller.set_camera(camera)

        weapon = self.spawn_actor(obj, "weapon", Weapon)
        if weapon is None:
            return

        controller.set_weapon(weapon)
        if pawn.weapon_attachment_class is not None:
            pawn.create_weapon_attachment(pawn.weapon_attachment_class)

    @contextmanager
    def protect_exemptions(self, exemptions):
        """Suspend and restore state of exempted actors around an operation

        :param exemptions: Iterable of exempt Actor instances"""
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
        """Listener for MapLoadedSignal
        Attempts to create network entities from BGE proxies"""
        scene = logic.getCurrentScene()

        found_actors = {}

        # Conversion step
        for obj in scene.objects:
            actor = self.spawn_actor(obj, "replicable", Actor)

            if actor is None:
                continue

            print("Loaded {}".format(actor))
            found_actors[obj] = actor

            actor.world_position = obj.worldPosition.copy()
            actor.world_rotation = obj.worldOrientation.to_euler()

            if isinstance(actor, Pawn):
                self.create_pawn_controller(actor, obj)

        # Establish parent relationships
        for obj, actor in found_actors.items():
            if obj.parent in found_actors:
                actor.set_parent(found_actors[obj.parent])
            obj.endObject()

    @PhysicsSingleUpdateSignal.global_listener
    def update_for(self, delta_time, target):
        """Listener for PhysicsSingleUpdateSignal
        Attempts to update physics simulation for single actor

        :param delta_time: Time to progress simulation
        :param target: Actor instance to update state"""
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
        """Listener for PhysicsTickSignal
        Updates Physics simulation for entire world

        :param scene: BGE scene reference
        :param delta_time: Time to progress simulation"""
        self._update_func(delta_time)
        self._apply_func()

        UpdateCollidersSignal.invoke()

    @CopyStateToActor.global_listener
    def copy_to_actor(self, state, actor):
        """Copy state information from source to target

        :param source_state: State to copy from
        :param target_state: State to copy to"""
        actor.world_position = state.position.copy()
        actor.world_velocity = state.velocity.copy()
        actor.world_angular = state.angular.copy()
        actor.world_rotation = state.rotation.copy()
        actor.collision_group = state.collision_group
        actor.collision_mask = state.collision_mask

    @CopyActorToState.global_listener
    def copy_to_state(self, actor, state):
        """Copy state information from source to target

        :param source_state: State to copy from
        :param target_state: State to copy to"""
        state.position = actor.world_position.copy()
        state.velocity = actor.world_velocity.copy()
        state.angular = actor.world_angular.copy()
        state.rotation = actor.world_rotation.copy()
        state.collision_group = actor.collision_group
        state.collision_mask = actor.collision_mask


@with_tag(Netmodes.server)
class ServerPhysics(PhysicsSystem):

    def save_network_states(self):
        """Saves Physics transformations to network variables"""
        for replicable in WorldInfo.subclass_of(Actor):
            replicable.copy_state_to_network()

    @PhysicsTickSignal.global_listener
    def update(self, scene, delta_time):
        """Listener for PhysicsTickSignal
        Copy physics state to network variable for Actor instances"""
        super().update(scene, delta_time)

        self.save_network_states()


@with_tag(Netmodes.client)
class ClientPhysics(PhysicsSystem):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._extrapolators = defaultdict(EPICExtrapolator)

    def extrapolate_network_states(self):
        """Apply state from extrapolators to replicated actors"""
        current_time = WorldInfo.elapsed
        simulated_proxy = Roles.simulated_proxy
        for replicable, extrapolator in self._extrapolators.items():
            result = extrapolator.read_sample(current_time)

            if replicable.roles.local != simulated_proxy:
                continue

            position, velocity = result

            replicable.world_position = position
            replicable.world_velocity = velocity

    def spawn_actor(self, lookup, name, type_of):
        """Overrides spawning for clients to ensure only static actors spawn"""
        if not name + "_id" in lookup:
            return

        return super().spawn_actor(lookup, name, type_of)

    @PhysicsReplicatedSignal.global_listener
    def on_physics_replicated(self, timestamp, position, velocity, target):
        if type(target).type_name != "Barrel":
            return

        if not hasattr(target, "f"):
            target.f = target.object.scene.addObject("Flag", target.object)

        target.f.worldPosition=position
        extrapolator = self._extrapolators[target]
        extrapolator.add_sample(timestamp, WorldInfo.elapsed, target.world_position, position, velocity)

    @ReplicableUnregisteredSignal.global_listener
    def on_replicable_unregistered(self, target):
        if target in self._extrapolators:
            self._extrapolators.pop(target)

    @PhysicsTickSignal.global_listener
    def update(self, scene, delta_time):
        """Listener for PhysicsTickSignal
        Copy physics state to network variable for Actor instances"""
        super().update(scene, delta_time)

        self.extrapolate_network_states()


@with_tag(Netmodes.client)
class ClienstPhysics(PhysicsSystem):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._interpolation_buffers = defaultdict(self.create_interpolator)

    def create_interpolator(self):
        return Interpolator(0.1)

    def interpolate_states(self):
        """Apply state from interpolation buffers to replicated actors"""
        current_time = WorldInfo.elapsed
        simulated_proxy = Roles.simulated_proxy
        for replicable, interpolation_buffer in self._interpolation_buffers.items():

            result = interpolation_buffer.read_sample()
            if replicable.roles.local != simulated_proxy:
                continue

            if result is None:
                continue
            position, velocity = result

            replicable.world_position = position
            replicable.world_velocity = velocity

    def spawn_actor(self, lookup, name, type_of):
        """Overrides spawning for clients to ensure only static actors spawn"""
        if not name + "_id" in lookup:
            return

        return super().spawn_actor(lookup, name, type_of)

    @PhysicsReplicatedSignal.global_listener
    def on_physics_replicated(self, timestamp, position, velocity, target):
        buffer = self._interpolation_buffers[target]
        buffer.add_sample(timestamp, (position, velocity))

    @ReplicableUnregisteredSignal.global_listener
    def on_replicable_unregistered(self, target):
        if target in self._interpolation_buffers:
            self._interpolation_buffers.pop(target)

    @PhysicsTickSignal.global_listener
    def update(self, scene, delta_time):
        """Listener for PhysicsTickSignal
        Copy physics state to network variable for Actor instances"""
        super().update(scene, delta_time)

        self.interpolate_states()


class Interpolator:
    def __init__(self, offset):
        self.samples = []
        self.offset = offset

        self.calibration = None

    def add_sample(self, timestamp, sample):
        self.samples.append((timestamp, sample))

        from time import monotonic
        if self.calibration is None:
            self.calibration = timestamp - monotonic()

    def read_sample(self):

        from time import monotonic
        projected_time = monotonic() + self.calibration + .5
        if self.samples:
            print("\n",projected_time, self.samples[-1][0])

        last_entry = None
        for entry in self.samples:
            timestamp, *_ = entry

            if timestamp > projected_time:
                break

            last_entry = entry

        else:
            return None

        factor = (projected_time - last_entry[0]) / (timestamp - last_entry[0])

        data = []
        for old_state, new_state in zip(last_entry[1], entry[1]):
            data.append(old_state.lerp(new_state, factor))

        return data




class EPICExtrapolator:

    MINIMUM_DT = 0.01

    def __init__(self):
        self._update_time = 0.0
        self._last_timestamp = 0.0
        self._snap_timestamp = 0.0
        self._target_timestamp = 0.0

        self._snap_position = Vector()
        self._target_position = Vector()
        self._snap_velocity = Vector()
        self._last_position = Vector()

    def add_sample(self, timestamp, current_time, current_position, position, velocity=None):
        if velocity is None:
            velocity = self.determine_velocity(timestamp, position)

        if timestamp <= self._last_timestamp:
            return

        position = position.copy()
        velocity = velocity.copy()

        self.update_estimates(timestamp)

        self._last_position = position
        self._last_timestamp = timestamp

        self._snap_position = current_position.copy()

        self._target_timestamp = current_time + self._update_time
        delta_time = self._target_timestamp - timestamp
        self._target_position = position + velocity * delta_time
        self._snap_timestamp = current_time

        if abs(self._target_timestamp - self._snap_timestamp) < self.__class__.MINIMUM_DT:
            self._snap_velocity = velocity

        else:
            delta_time = 1.0 / (self._target_timestamp - self._snap_timestamp)
            self._snap_velocity = (self._target_position - self._snap_position) * delta_time

    def determine_velocity(self, timestamp, position):
        if abs(timestamp - self._last_timestamp) > self.__class__.MINIMUM_DT:
            delta_time = 1.0 / (timestamp - self._last_timestamp)
            velocity = (position - self._last_position) * delta_time

        else:
            velocity = Vector()

        return velocity

    def read_sample(self, request_time):
        max_timestamp = self._target_timestamp + self._update_time

        valid = True
        if request_time < self._snap_timestamp:
            request_time = self._snap_timestamp
            valid = False

        if request_time > max_timestamp:
            request_time = max_timestamp
            valid = False

        velocity = self._snap_velocity.copy()
        position = self._snap_position + velocity * (request_time - self._snap_timestamp)
        if not valid:
            velocity.zero()

        return position, velocity

    def reset(self, timestamp, current_time, position, velocity):
        assert timestamp <= current_time
        self._last_timestamp = timestamp
        self._last_position = position
        self._snap_timestamp = current_time
        self._snap_position = position
        self._update_time = current_time - timestamp
        self._target_timestamp = current_time + self._update_time
        self._snap_velocity = velocity
        self._target_position = position + velocity * self._update_time

    def update_estimates(self, timestamp):
        update_time = timestamp - self._last_timestamp
        if update_time > self._update_time:
            self._update_time = (self._update_time + update_time) * 0.5

        else:
            self._update_time = (self._update_time * 7 + update_time) * 0.125