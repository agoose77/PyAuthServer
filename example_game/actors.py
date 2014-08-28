from math import radians, sin

from network.decorators import requires_netmode, simulated
from network.descriptors import Attribute
from network.enums import Netmodes, Roles
from network.replicable import Replicable

from game_system.entities import Actor, Camera, Pawn, Projectile, WeaponAttachment
from game_system.controllers import PlayerController
from game_system.enums import Axis, CollisionState
from game_system.signals import BroadcastMessage, CollisionSignal, LogicUpdateSignal, PawnKilledSignal
from game_system.timer import Timer
from game_system.math import lerp

from .enums import TeamRelation
from .signals import UIHealthChangedSignal


__all__ = ["TestBox", "ArrowProjectile", "Barrel", "BowAttachment", "CTFPawn", "CTFFlag", "Cone", "Palette", "SpawnPoint"]


class CameraAnimationActor(Camera):

    entity_name = "Camera"

    def on_initialised(self):
        super().on_initialised()

        displacement = (self.physics.get_direction(Axis.y) + self.physics.get_direction(Axis.z)*0.3) * 50

        self.orbit_frequency = 1 / 40
        self.origin = Vector((0, -20, 20))
        self.physics.world_position = self.origin + displacement

    @LogicUpdateSignal.global_listener
    @simulated
    def update(self, delta_time):
        from_origin = self.physics.world_position - self.origin
        from_origin.rotate(Euler((0, 0, radians(360) * delta_time * self.orbit_frequency)))

        self.physics.world_position = self.origin + from_origin
        #self.physics.align_to(-from_origin, factor=.43, axis=Axis.y)


class ArrowProjectile(Projectile):
    entity_name = "Arrow"

    def on_initialised(self):
        super().on_initialised()

        self.lifespan = 15

    @LogicUpdateSignal.global_listener
    @simulated
    def update(self, delta_time):
        if not self.in_flight:
            return

        self.align_to(self.world_velocity, factor=0.3)

    @requires_netmode(Netmodes.server)
    def server_deal_damage(self, collision_result):
        weapon = self.owner

        # If the weapon disappears before projectile
        if not weapon:
            return

        hit_entity = collision_result.entity
        if not isinstance(hit_entity, Pawn):
            return

        # Get pawn's team
        pawn_team = hit_entity.info.team

        # Get weapon's owner (controller)
        instigator = weapon.owner
        instigator_team = instigator.info.team

        # Get team relationship
        relationship = instigator_team.get_relationship_with(pawn_team)

        # If we aren't enemies
        if relationship != TeamRelation.enemy:
            return

        super().server_deal_damage(collision_result)


class Barrel(Actor):
    entity_name = "Barrel"

    @CollisionSignal.listener
    @requires_netmode(Netmodes.client)
    @simulated
    def on_collision(self, collision_result):
        if not collision_result.state == CollisionState.started:
            return

        player_controller = PlayerController.get_local_controller()

        collision_sound = self.resources['sounds']['clang.mp3']
        player_controller.hear_sound(collision_sound, self.physics.world_position, self.physics.world_orientation,
                                     self.physics.world_velocity)


class BowAttachment(WeaponAttachment):

    roles = Attribute(Roles(local=Roles.authority, remote=Roles.simulated_proxy))

    entity_name = "Bow"


class CTFPawn(Pawn):
    entity_name = "Suzanne_Physics"

    flag = Attribute(type_of=Replicable, complain=True, notify=True)

    def conditions(self, is_owner, is_complaint, is_initial):
        yield from super().conditions(is_owner, is_complaint, is_initial)

        if is_complaint:
            yield "flag"

    @simulated
    def attach_flag(self, flag):
        # Store reference
        self._flag = flag
        # Network info
        flag.possessed_by(self)
        # Physics info
        flag.set_parent(self, "weapon")
        flag.local_position = Vector()

    @simulated
    def remove_flag(self):
        self._flag = None
        # Network info
        self._flag.unpossessed()
        # Physics info
        self._flag.remove_parent()

    @simulated
    def on_flag_replicated(self, flag):
        """Called when flag is changed"""
        if flag is None:
            self.remove_flag()

        else:
            self.attach_flag(flag)

    def on_notify(self, name):
        # play weapon effects
        if name == "health":
            UIHealthChangedSignal.invoke(self.health)

        elif name == "flag":
            self.on_flag_replicated(self.flag)

        else:
            super().on_notify(name)

    def on_initialised(self):
        super().on_initialised()

        self.walk_speed = 12
        self.run_speed = 18

        self._flag = None


class CTFFlag(Actor):
    owner_info_possessed = Attribute(type_of=Replicable, complain=True)

    entity_name = "Flag"
    colours = {TeamRelation.friendly: [0, 255, 0, 1], TeamRelation.enemy: [255, 0, 0, 1],
               TeamRelation.neutral: [255, 255, 255, 1]}

    def on_initialised(self):
        super().on_initialised()

        self.indestructable = True
        self.replicate_physics_to_owner = False

        self.floor_offset_minimum = 1.0
        self.floor_offset_maximum = 2.5

        omega = radians(360) / 3
        self._position_timer = Timer(end=omega, repeat=True, active=True)
        self._position_timer.on_update = self.update_position

    def possessed_by(self, other):
        super().possessed_by(other)

        # Network info
        self.owner_info_possessed = other.info

        # Inform other players
        BroadcastMessage.invoke("{} has picked up flag"
                                .format(self.owner_info_possessed.name))

    def unpossessed(self):
        # Inform other players
        BroadcastMessage.invoke("{} has dropped flag"
                                .format(self.owner_info_possessed.name))

        self.owner_info_possessed = None

        super().unpossessed()

    @property
    def in_use(self):
        return bool(self.owner_info_possessed)

    @requires_netmode(Netmodes.client)
    @simulated
    @LogicUpdateSignal.global_listener
    def update(self, delta_time):
        self.update_colour()

    @simulated
    def update_colour(self):
        if not self.in_use:
            team_relation = TeamRelation.neutral

        else:
            player_controller = PlayerController.get_local_controller()
            if not player_controller:
                return

            player_team = player_controller.info.team
            if not player_team:
                return

            team_relation = player_team.get_relationship_with(self.owner_info_possessed.team)

        self.colour = self.colours[team_relation]

    @requires_netmode(Netmodes.server)
    def update_position(self):
        if self.in_use:
            return

        timer_progress = self._position_timer.progress
        divided_position = (1 + sin(radians(360 * timer_progress)))/2

        ray_result = self.trace_ray(self.physics.world_position - self.physics.get_direction(Axis.z), distance=100)
        if ray_result is None:
            return

        relative_position_z = lerp(self.floor_offset_minimum, self.floor_offset_maximum, divided_position)
        self.physics.world_position = ray_result.position + ray_result.normal * relative_position_z

    def conditions(self, is_owner, is_complaint, is_initial):
        yield from super().conditions(is_owner, is_complaint, is_initial)

        if is_complaint:
            yield "owner_info_possessed"


class Cone(Actor):
    entity_name = "Cone"


class Palette(Actor):
    entity_name = "Palette"


class SpawnPoint(Actor):

    roles = Roles(Roles.authority, Roles.none)

    entity_name = "SpawnPoint"


class TestBox(Actor):

    roles = Roles(Roles.authority, Roles.simulated_proxy)

    @LogicUpdateSignal.global_listener
    def update(self, delta_time):
        orientation = self.physics.world_orientation
        orientation.z += 6.28 * delta_time / 2
        self.physics.world_orientation = orientation


class DeathPlane(Actor):
    entity_name = "Plane"

    roles = Attribute(Roles(Roles.authority, Roles.none))

    @CollisionSignal.listener
    def on_collision(self, collision_result):
        if not collision_result.state == CollisionState.started:
            return

        if not isinstance(collision_result.entity, Pawn):
            return

        PawnKilledSignal.invoke(self, target=collision_result.entity)