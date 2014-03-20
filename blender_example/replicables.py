from bge_network import *
from behaviours import *
from bge import logic

import signals
import aud
import controls
import math
import mathutils
import bge

from enums import TeamRelation


class GameReplicationInfo(ReplicableInfo):
    roles = Attribute(
                      Roles(
                            Roles.authority,
                            Roles.simulated_proxy
                            )
                      )

    time_to_start = Attribute(0.0)
    match_started = Attribute(False)
    players = Attribute(TypedList(Replicable),
                        element_flag=TypeFlag(Replicable))


    @requires_netmode(Netmodes.server)
    @BroadcastMessage.global_listener
    def send_broadcast(self, message):
        player_controllers = WorldInfo.subclass_of(PlayerController)

        for controller in player_controllers:
            controller.receive_broadcast(message)

    def conditions(self, is_owner, is_complaint, is_initial):
        yield from super().conditions(is_owner, is_complaint, is_initial)

        yield "match_started"
        yield "time_to_start"
        yield "players"


class TeamInfo(ReplicableInfo):

    name = Attribute(type_of=str, complain=True)
    score = Attribute(0, complain=True)
    players = Attribute(TypedSet(Replicable),
                        element_flag=TypeFlag(Replicable))

    @simulated
    def get_relationship_with(self, team):
        return(TeamRelation.friendly if team == self else TeamRelation.enemy)

    def conditions(self, is_owner, is_complaint, is_initial):
        yield from super().conditions(is_owner, is_complaint, is_initial)

        if is_complaint:
            yield "name"
            yield "score"

        yield "players"


class CTFPlayerReplicationInfo(PlayerReplicationInfo):

    team = Attribute(type_of=Replicable, complain=True)

    def conditions(self, is_owner, is_complain, is_initial):
        yield from super().conditions(is_owner, is_complain, is_initial)

        if is_complain:
            yield "team"


class EnemyController(AIController):

    def on_initialised(self):
        super().on_initialised()

        behaviour = SelectorNode(
                                 dying_behaviour(),
                                 attack_behaviour(),
                                 idle_behaviour()
                                 )

        behaviour.should_restart = True
        self.behaviour.root = behaviour


class CTFPlayerController(PlayerController):

    input_fields = ("forward", "backwards", "left",
                    "right", "shoot", "run", "voice",
                    "jump")

    def clear_inventory(self):
        for item in self.inventory:
            item.unpossessed()
        self.inventory.clear()

    @CollisionSignal.listener
    def on_collision(self, other, is_new, data):
        target = Actor.from_object(other)
        if target is None or not is_new:
            return

        if isinstance(target, CTFFlag):
            self.pickup_flag(target)

    def on_initialised(self):
        super().on_initialised()

        behaviour = SequenceNode(
                                 controls.camera_control(),
                                 controls.inputs_control()
                                 )

        behaviour.should_restart = True
        self.behaviour.root.add_child(behaviour)

        self.inventory = []

    @ActorKilledSignal.listener
    def on_killed(self, attacker, target):
        self.clear_inventory()

    def on_unregistered(self):
        super().on_unregistered()

        self.clear_inventory()

    def on_notify(self, name):
        super().on_notify(name)

        if name == "weapon":
            signals.UIWeaponChangedSignal.invoke(self.weapon)
            signals.UIWeaponDataChangedSignal.invoke("ammo", self.weapon.ammo)
            #signals.UIWeaponDataChangedSignal.invoke("clips", self.weapon.clips)

        if name == "pawn":
            signals.UIHealthChangedSignal.invoke(self.pawn.health)

    def pickup_flag(self, flag):
        flag.possessed_by(self)
        flag.owner_info_possessed = self.info
        flag.set_parent(self.pawn, "weapon")
        flag.local_position = mathutils.Vector()
        self.inventory.append(flag)

    @PlayerInputSignal.global_listener
    def player_update(self, delta_time):
        super().player_update(delta_time)

        # Only record when we need to
        if self.inputs.voice != self.microphone.active:
            self.microphone.active = self.inputs.voice

    @ActorDamagedSignal.listener
    def take_damage(self, damage, instigator, hit_position, momentum):
        if self.pawn.health == 0:
            ActorKilledSignal.invoke(instigator, target=self.pawn)


class CTFPawn(Pawn):
    entity_name = "Suzanne_Physics"

    @simulated
    def on_notify(self, name):
        # play weapon effects
        if name == "health":
            signals.UIHealthChangedSignal.invoke(self.health)

        else:
            super().on_notify(name)

    def on_initialised(self):
        super().on_initialised()

        self.walk_speed = 3
        self.run_speed = 6


class BowWeapon(ProjectileWeapon):

    def on_notify(self, name):
        # This way ammo is still updated locally
        if name == "ammo":
            signals.UIWeaponDataChangedSignal.invoke("ammo", self.ammo)

        else:
            super().on_notify(name)

    def on_initialised(self):
        super().on_initialised()

        self.max_ammo = 60
        self.attachment_class = BowAttachment

        self.shoot_interval = 0.6
        self.theme_colour = [0.0, 0.50, 0.93, 1.0]

        self.projectile_class = ArrowProjectile
        self.projectile_velocity = mathutils.Vector((0, 15, 0))


class TracerParticle(Particle):
    entity_name = "Trace"

    def on_initialised(self):
        super().on_initialised()

        self.lifespan = 0.5
        self.scale = self.object.localScale.copy()

    @UpdateSignal.global_listener
    def update(self, delta_time):
        self.object.localScale = self.scale * (1 - self._timer.progress) ** 2


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


class BowAttachment(WeaponAttachment):

    roles = Attribute(Roles(local=Roles.authority,
                            remote=Roles.simulated_proxy))

    entity_name = "Bow"


class SpawnPoint(Actor):

    roles = Roles(Roles.authority,
                              Roles.none)

    entity_name = "SpawnPoint"


class CTFFlag(ResourceActor):
    a = Attribute("")
    owner_info_possessed = Attribute(type_of=Replicable,
                                     notify=True,
                                     complain=True)

    entity_name = "Flag"
    colours = {TeamRelation.friendly: [0, 255, 0, 1],
                TeamRelation.enemy: [255, 0, 0, 1],
                TeamRelation.neutral: [255, 255, 255, 1]}

    def on_initialised(self):
        super().on_initialised()
        self.a = "DEBUG"
        self.replicate_physics_to_owner = False

    def possessed_by(self, other):
        super().possessed_by(other)
        assert other.info
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
        yield "a"
        if is_complaint:
            yield "owner_info_possessed"


class Cone(Actor):
    entity_name = "Cone"

