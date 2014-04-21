from network.decorators import requires_netmode, simulated
from network.descriptors import Attribute
from network.enums import Netmodes, Roles
from network.iterators import take_first
from network.replicable import Replicable
from network.signals import UpdateSignal
from network.world_info import WorldInfo

from bge_network.actors import Actor, Pawn, ResourceActor, WeaponAttachment
from bge_network.controllers import PlayerController
from bge_network.signals import BroadcastMessage, CollisionSignal
from bge_network.utilities import mean

from aud import Factory, device as Device
from bge import logic

from .enums import TeamRelation
from .particles import TracerParticle
from .signals import UIHealthChangedSignal

__all__ = ["ArrowProjectile", "Barrel", "BowAttachment", "CTFPawn", "CTFFlag",
           "Cone", "Palette", "SpawnPoint"]


class ArrowProjectile(Actor):
    entity_name = "Arrow"

    def on_registered(self):
        super().on_registered()

        self.replicate_temporarily = True
        self.in_flight = True
        self.lifespan = 5

    @UpdateSignal.global_listener
    @simulated
    def update(self, delta_time):
        if not self.in_flight:
            return

        global_vel = self.velocity.copy()
        global_vel.rotate(self.rotation)

        TracerParticle().position = self.position - global_vel.normalized() * 2
        self.align_to(global_vel, 0.3)

    @CollisionSignal.listener
    @simulated
    def on_collision(self, other, is_new, data):
        target = self.from_object(other)

        if not data or not is_new or not self.in_flight:
            return

        hit_normal = mean(c.hitNormal for c in data)
        hit_position = mean(c.hitPosition for c in data)

        if isinstance(target, Pawn) and self.owner:
            momentum = self.mass * self.velocity.length * hit_normal

            ActorDamagedSignal.invoke(self.owner.base_damage,
                                                  self.owner.owner,
                                                  hit_position, momentum,
                                                  target=target)

        self.request_unregistration()
        self.in_flight = False


class Barrel(Actor):
    entity_name = "Barrel"

    @CollisionSignal.listener
    @requires_netmode(Netmodes.client)
    @simulated
    def on_collision(self, other, is_new, data):
        if not is_new:
            return

        file_path = logic.expandPath("//data/Barrel/clang.mp3")
        factory = Factory.file(file_path)
        return Device().play(factory)


class BowAttachment(WeaponAttachment):

    roles = Attribute(Roles(local=Roles.authority,
                            remote=Roles.simulated_proxy))

    entity_name = "Bow"


class CTFPawn(Pawn):
    entity_name = "Suzanne_Physics"

    @simulated
    def on_notify(self, name):
        # play weapon effects
        if name == "health":
            UIHealthChangedSignal.invoke(self.health)

        else:
            super().on_notify(name)

    def on_initialised(self):
        super().on_initialised()

        self.walk_speed = 3
        self.run_speed = 6


class CTFFlag(ResourceActor):
    owner_info_possessed = Attribute(type_of=Replicable,
                                     notify=True,
                                     complain=True)

    entity_name = "Flag"
    colours = {TeamRelation.friendly: [0, 255, 0, 1],
                TeamRelation.enemy: [255, 0, 0, 1],
                TeamRelation.neutral: [255, 255, 255, 1]}

    def on_initialised(self):
        super().on_initialised()

        self.replicate_physics_to_owner = False

    def possessed_by(self, other):
        super().possessed_by(other)
        # Inform other players
        BroadcastMessage.invoke("{} has picked up flag"
                                .format(other.info.name))

    def unpossessed(self):
        # Inform other players
        assert self.owner.info
        BroadcastMessage.invoke("{} has dropped flag"
                                .format(self.owner.info.name))
        self.owner_info_possessed = None

        super().unpossessed()

    def on_notify(self, name):
        if name == "owner_info_possessed":

            if self.owner_info_possessed is None:
                self.colour = self.colours[TeamRelation.neutral]
                return

            player_controller = take_first(WorldInfo.subclass_of(
                                                     PlayerController))
            assert player_controller.info
            team_relation = player_controller.info.team.get_relationship_with(
                                              self.owner_info_possessed.team)

            self.colour = self.colours[team_relation]

        else:
            super().on_notify(name)

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

