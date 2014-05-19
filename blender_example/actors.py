from network.decorators import requires_netmode, simulated
from network.descriptors import Attribute
from network.enums import Netmodes, Roles
from network.iterators import take_single
from network.replicable import Replicable
from network.signals import UpdateSignal
from network.world_info import WorldInfo

from bge_network.actors import Actor, Pawn, Projectile, ResourceActor, WeaponAttachment
from bge_network.controllers import PlayerController
from bge_network.enums import CollisionType
from bge_network.mesh import BGEMesh
from bge_network.signals import ActorDamagedSignal, BroadcastMessage, CollisionSignal
from bge_network.utilities import mean

from aud import Factory, device as Device
from bge import logic
from mathutils import Vector

from .enums import TeamRelation
from .particles import TracerParticle
from .signals import UIHealthChangedSignal
from .replication_infos import TeamReplicationInfo

__all__ = ["ArrowProjectile", "Barrel", "BowAttachment", "CTFPawn", "CTFFlag",
           "Cone", "Palette", "SpawnPoint"]


class ArrowProjectile(Projectile):
    entity_name = "Arrow"

    @UpdateSignal.global_listener
    @simulated
    def update(self, delta_time):
        if not self.in_flight:
            return

        global_vel = self.velocity.copy()
        global_vel.rotate(self.rotation)

        TracerParticle().position = self.position - global_vel.normalized() * 2
        self.align_to(global_vel, 0.3)

    @requires_netmode(Netmodes.server)
    def server_deal_damage(self, collision_info, hit_pawn):
        weapon = self.owner

        # If the weapon disappears before projectile
        if not weapon:
            return

        # Get pawn's team
        pawn_team = hit_pawn.info.team

        # Get weapon's owner (controller)
        instigator = weapon.owner
        instigator_team = instigator.info.team

        # Get team relationship
        relationship = instigator_team.get_relationship_with(pawn_team)

        # If we aren't enemies
        if relationship != TeamRelation.enemy:
            return

        super().server_deal_damage(collision_info, hit_pawn)


class Barrel(Actor):
    entity_name = "Barrel"

    @CollisionSignal.listener
    @requires_netmode(Netmodes.client)
    @simulated
    def on_collision(self, other, collision_type, collision_data):
        if not collision_type == CollisionType.started:
            return

        player_controller = PlayerController.get_local_controller()

        collision_sound = self.resources['sounds']['clang.mp3']
        player_controller.hear_sound(collision_sound, self.position,
                                    self.rotation, self.velocity)


class BowAttachment(WeaponAttachment):

    roles = Attribute(Roles(local=Roles.authority,
                            remote=Roles.simulated_proxy))

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


class CTFFlag(ResourceActor):
    owner_info_possessed = Attribute(type_of=Replicable, complain=True)

    entity_name = "Flag"
    colours = {TeamRelation.friendly: [0, 255, 0, 1],
                TeamRelation.enemy: [255, 0, 0, 1],
                TeamRelation.neutral: [255, 255, 255, 1]}

    def on_initialised(self):
        super().on_initialised()

        self.replicate_physics_to_owner = False

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

    @UpdateSignal.global_listener
    @requires_netmode(Netmodes.client)
    @simulated
    def update(self, delta_time):
        flag_owner_info = self.owner_info_possessed

        if flag_owner_info is None:
            team_relation = TeamRelation.neutral

        else:
            player_controller = PlayerController.get_local_controller()
            if not player_controller:
                return
            player_team = player_controller.info.team
            if not player_team:
                return
            team_relation = player_team.get_relationship_with(
                                              flag_owner_info.team)

        self.colour = self.colours[team_relation]

    def conditions(self, is_owner, is_complaint, is_initial):
        yield from super().conditions(is_owner, is_complaint, is_initial)

        if is_complaint:
            yield "owner_info_possessed"


class Cone(Actor):
    entity_name = "Cone"


class Palette(Actor):
    entity_name = "Palette"


class SpawnPoint(Actor):

    roles = Roles(Roles.authority,
                              Roles.none)

    entity_name = "SpawnPoint"

