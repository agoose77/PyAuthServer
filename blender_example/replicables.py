import bge_network
from behaviours import *
from bge import logic

import signals
import aud
import controls
import math
import mathutils
import bge

from enums import TeamRelation


class GameReplicationInfo(bge_network.ReplicableInfo):
    roles = bge_network.Attribute(
                                  bge_network.Roles(
                                                    bge_network.Roles.authority,
                                                    bge_network.Roles.simulated_proxy
                                                    )
                                  )

    time_to_start = bge_network.Attribute(0.0)
    match_started = bge_network.Attribute(False)
    players = bge_network.Attribute(bge_network.TypedList(bge_network.Replicable),
                                    element_flag=bge_network.TypeFlag(bge_network.Replicable))

    def conditions(self, is_owner, is_complaint, is_initial):
        yield from super().conditions(is_owner, is_complaint, is_initial)

        yield "match_started"
        yield "time_to_start"
        yield "players"


class TeamInfo(bge_network.ReplicableInfo):

    name = bge_network.Attribute(type_of=str, complain=True)
    score = bge_network.Attribute(0, complain=True)
    players = bge_network.Attribute(bge_network.TypedSet(bge_network.Replicable),
                    element_flag=bge_network.TypeFlag(bge_network.Replicable))

    @bge_network.simulated
    def get_relationship_with(self, team):
        return(TeamRelation.friendly if team == self else TeamRelation.enemy)

    def conditions(self, is_owner, is_complaint, is_initial):
        yield from super().conditions(is_owner, is_complaint, is_initial)

        if is_complaint:
            yield "name"
            yield "score"

        yield "players"


class CTFPlayerReplicationInfo(bge_network.PlayerReplicationInfo):

    team = bge_network.Attribute(type_of=bge_network.Replicable, complain=True)

    def conditions(self, is_owner, is_complain, is_initial):
        yield from super().conditions(is_owner, is_complain, is_initial)

        if is_complain:
            yield "team"


class EnemyController(bge_network.AIController):

    def on_initialised(self):
        super().on_initialised()

        behaviour = SelectorNode(
                                 dying_behaviour(),
                                 attack_behaviour(),
                                 idle_behaviour()
                                 )

        behaviour.should_restart = True
        self.behaviour.root = behaviour


class CTFPlayerController(bge_network.PlayerController):

    input_fields = ("forward", "backwards", "left",
                    "right", "shoot", "run", "voice",
                    "jump")

    @bge_network.CollisionSignal.listener
    def on_collision(self, other, is_new, data):
        target = bge_network.Actor.from_object(other)
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

    @bge_network.PlayerInputSignal.global_listener
    def player_update(self, delta_time):
        super().player_update(delta_time)

        # Only record when we need to
        if self.inputs.voice != self.microphone.active:
            self.microphone.active = self.inputs.voice

    @bge_network.ActorDamagedSignal.listener
    def take_damage(self, damage, instigator, hit_position, momentum):
        if self.pawn.health == 0:
            bge_network.ActorKilledSignal.invoke(instigator, target=self.pawn)


class CTFPawn(bge_network.Pawn):
    entity_name = "Suzanne_Physics"

    @bge_network.simulated
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


class Zombie(bge_network.Pawn):

    entity_name = "ZombieCollision"

    def on_initialised(self):
        super().on_initialised()

        animations = SelectorNode(
                                  dead_animation(),
                                  idle_animation(),
                                  walk_animation(),
                                )

        animations.should_restart = True

        self.animations.root.add_child(animations)

        self.walk_speed = 1
        self.run_speed = 6


class BowWeapon(bge_network.ProjectileWeapon):

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


class ZombieAttachment(bge_network.WeaponAttachment):

    entity_name = "EmptyWeapon"

    @simulated
    def play_fire_effects(self):
        self.owner.play_animation("Attack", 0, 60)


class TracerParticle(bge_network.Particle):
    entity_name = "Trace"

    def on_initialised(self):
        super().on_initialised()

        self.lifespan = 0.5
        self.scale = self.object.localScale.copy()

    @UpdateSignal.global_listener
    def update(self, delta_time):
        self.object.localScale = self.scale * (1 - self._timer.progress) ** 2


class ArrowProjectile(bge_network.Actor):
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

    @bge_network.CollisionSignal.listener
    @simulated
    def on_collision(self, other, is_new, data):
        target = self.from_object(other)

        if not data or not is_new or not self.in_flight:
            return

        hit_normal = bge_network.mean(c.hitNormal for c in data)
        hit_position = bge_network.mean(c.hitPosition for c in data)

        if isinstance(target, bge_network.Pawn) and self.owner:
            momentum = self.mass * self.velocity.length * hit_normal

            bge_network.ActorDamagedSignal.invoke(self.owner.base_damage,
                                                  self.owner.owner,
                                                  hit_position, momentum,
                                                  target=target)

        self.request_unregistration()
        self.in_flight = False


class ZombieWeapon(bge_network.TraceWeapon):

    def on_initialised(self):
        super().on_initialised()

        self.max_ammo = 1

        self.shoot_interval = 1
        self.maximum_range = 8
        self.effective_range = 6
        self.base_damage = 80
        self.attachment_class = ZombieAttachment

    def consume_ammo(self):
        pass


class BowAttachment(bge_network.WeaponAttachment):

    roles = bge_network.Attribute(bge_network.Roles(local=bge_network.Roles.authority,
                                                    remote=bge_network.Roles.simulated_proxy))

    entity_name = "Bow"


class SpawnPoint(bge_network.Actor):

    roles = bge_network.Roles(bge_network.Roles.authority,
                              bge_network.Roles.none)

    entity_name = "SpawnPoint"


class CTFFlag(bge_network.ResourceActor):
    owner_info_possessed = bge_network.Attribute(type_of=bge_network.Replicable,
                                            notify=True, complain=True)

    entity_name = "Flag"
    colours = {TeamRelation.friendly: [0, 255, 0, 1],
                TeamRelation.enemy: [255, 0, 0, 1]}

    def on_initialised(self):
        super().on_initialised()

        self.replicate_physics_to_owner = False

    def possessed_by(self, other):
        super().possessed_by(other)

        # Inform other players
        bge_network.BroadcastMessage.invoke("{} has picked up flag"
                                .format(other.info.name))

    def unpossessed(self):
        # Inform other players
        bge_network.BroadcastMessage.invoke("{} has dropped flag"
                                .format(self.owner.info.name))

        super().unpossessed()

    def on_notify(self, name):
        if name == "owner_info_possessed":
            player_controllers = bge_network.WorldInfo.subclass_of(
                                       bge_network.PlayerController)
            player_controller = next(player_controllers.__iter__())
            team_relation = player_controller.info.team.get_relationship_with(
                                         self.owner_info_possessed.team)

            self.colour = self.colours[team_relation]

        else:
            super().on_notify(name)

    def conditions(self, is_owner, is_complaint, is_initial):
        yield from super().conditions(is_owner, is_complaint, is_initial)

        if is_complaint:
            yield "owner_info_possessed"


class Cone(bge_network.Actor):
    entity_name = "Cone"

