from collections import defaultdict
from contextlib import contextmanager

from network.decorators import with_tag
from network.enums import Netmodes, Roles
from network.logger import logger
from network.tagged_delegate import DelegateByNetmode
from network.replicable import Replicable
from network.signals import SignalListener, ReplicableUnregisteredSignal
from network.world_info import WorldInfo

from game_system.entities import Actor, Camera, Pawn
from game_system.controllers import Controller
from game_system.weapons import Weapon
from game_system.replication_info import ReplicationInfo
from game_system.enums import PhysicsType
from game_system.physics import ClientPhysics, ServerPhysics
from game_system.signals import *

from bge import logic
from mathutils import Vector


__all__ = ["PhysicsSystem", "ServerPhysics", "ClientPhysics", "EPICExtrapolator"]


class BGEPhysicsBase:

    def __init__(self, update_func, apply_func):
        self.register_signals()

        self._update_func = update_func
        self._apply_func = apply_func
        self._active_physics = PhysicsType.dynamic, PhysicsType.rigid_body

    @staticmethod
    def on_conversion_error(lookup, err):
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
        controller = self.spawn_actor(obj, "controller", Controller)
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

            actor.transform.world_position = obj.worldPosition.copy()
            actor.transform.world_orientation = obj.worldOrientation.to_euler()

            if isinstance(actor, Pawn):
                self.create_pawn_controller(actor, obj)

        # Establish parent relationships
        for obj, actor in found_actors.items():
            if obj.parent in found_actors:
                actor.parent = found_actors[obj.parent]

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
    def update(self, delta_time):
        """Listener for PhysicsTickSignal
        Updates Physics simulation for entire world

        :param delta_time: Time to progress simulation"""
        self._update_func(delta_time)
        self._apply_func()

        UpdateCollidersSignal.invoke()


@with_tag("BGE")
class BGEServerPhysics(ServerPhysics, BGEPhysicsBase):

    pass


@with_tag("BGE")
class BGEClientPhysics(ClientPhysics, BGEPhysicsBase):

    def spawn_actor(self, lookup, name, type_of):
        """Overrides spawning for clients to ensure only static actors spawn"""
        if not name + "_id" in lookup:
            return

        return super().spawn_actor(lookup, name, type_of)