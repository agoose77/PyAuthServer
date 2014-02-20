import bge_network
from behaviours import *
from bge import logic

import signals
import aud
import controls
import math
import mathutils
import bge


class GameReplicationInfo(bge_network.ReplicableInfo):
    roles = bge_network.Attribute(
                                  bge_network.Roles(
                                                    bge_network.Roles.authority,
                                                    bge_network.Roles.simulated_proxy
                                                    )
                                  )

    time_to_start = bge_network.Attribute(0.0)
    match_started = bge_network.Attribute(False)

    def conditions(self, is_owner, is_complaint, is_initial):
        yield from super().conditions(is_owner, is_complaint, is_initial)

        yield "match_started"
        yield "time_to_start"


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


class Cone(bge_network.Actor):
    entity_name = "Cone"


class LegendController(bge_network.PlayerController):

    input_fields = ("forward", "backwards", "left",
                    "right", "shoot", "run", "voice")

    def on_notify(self, name):
        super().on_notify(name)

        if name == "weapon":
            signals.UIWeaponChangedSignal.invoke(self.weapon)
            signals.UIWeaponDataChangedSignal.invoke("ammo", self.weapon.ammo)
           #signals.UIWeaponDataChangedSignal.invoke("clips", self.weapon.clips)

        if name == "pawn":
            signals.UIHealthChangedSignal.invoke(self.pawn.health)

    @bge_network.ActorDamagedSignal.listener
    def take_damage(self, damage, instigator, hit_position, momentum):
        if self.pawn.health == 0:
            bge_network.ActorKilledSignal.invoke(instigator, target=self.pawn)

    def receive_broadcast(self, message_string: bge_network.TypeFlag(str)) -> bge_network.Netmodes.client:
        signals.ConsoleMessage.invoke(message_string)

    def on_initialised(self):
        super().on_initialised()

        behaviour = SequenceNode(
                                 controls.camera_control(),
                                 controls.inputs_control()
                                 )

        behaviour.should_restart = True
        self.behaviour.root.add_child(behaviour)

    @bge_network.PlayerInputSignal.global_listener
    def player_update(self, delta_time):
        super().player_update(delta_time)

        # Only record when we need to
        if self.inputs.voice != self.microphone.active:
            self.microphone.active = self.inputs.voice


class RobertNeville(bge_network.Pawn):
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


class M4A1Weapon(bge_network.ProjectileWeapon):

    def on_notify(self, name):
        # This way ammo is still updated locally
        if name == "ammo":
            signals.UIWeaponDataChangedSignal.invoke("ammo", self.ammo)
        else:
            super().on_notify(name)

    def on_initialised(self):
        super().on_initialised()

        self.max_ammo = 50
        self.attachment_class = M4A1Attachment

        self.shoot_interval = 0.3
        self.theme_colour = [0.53, 0.94, 0.28, 1.0]

        self.projectile_class = ArrowProjectile
        self.projectile_velocity = mathutils.Vector((0, 15, 10))


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


class SphereProjectile(bge_network.Actor):
    entity_name = "Sphere"

    def on_registered(self):
        super().on_registered()

        self.start_colour = mathutils.Vector(self.object.color)
        self.update_simulated_physics = False
        self.lifespan = 10

    @UpdateSignal.global_listener
    @requires_netmode(Netmodes.client)
    @simulated
    def update(self, delta_time):
        particle = TracerParticle()
        particle.position = self.position

        global_vel = self.velocity.copy()
        global_vel.rotate(self.rotation)
        global_rotation = mathutils.Vector().rotation_difference(global_vel)

        axis_spin = mathutils.Euler((0, (math.pi) * self._timer.progress, 0))
        axis_spin.rotate(global_rotation)
        particle.rotation = axis_spin

        self.object.color = bge_network.utilities.lerp(self.start_colour,
                                            mathutils.Vector((1, 0, 0, 1)),
                                            self._timer.progress)
        particle.object.color = self.object.color

    @bge_network.CollisionSignal.listener
    def on_collision(self, other, is_new, data):
        target = self.from_object(other)
        if not data or not is_new:
            return

        hit_normal = sum((c.hitNormal for c in data), Vector()) / len(data)
        hit_position = sum((c.hitPosition for c in data), Vector()) / len(data)

        if target is not None:
            momentum = self.mass * self.velocity.length * hit_normal

            bge_network.ActorDamagedSignal.invoke(self.owner.base_damage, self.owner.owner,
                                                  hit_position, momentum,
                                                  target=target)

            self.request_unregistration()


class ArrowProjectile(bge_network.Actor):
    entity_name = "Arrow"

    def on_registered(self):
        super().on_registered()

        self.update_simulated_physics = False
        self.in_flight = True

    @UpdateSignal.global_listener
    @simulated
    def update(self, delta_time):
        global_vel = self.velocity.copy()
        global_vel.rotate(self.rotation)

        if self.in_flight:
            self.align_to(global_vel, 0.3)

    @bge_network.CollisionSignal.listener
    @simulated
    def on_collision(self, other, is_new, data):
        target = self.from_object(other)

        if not data or not is_new or not self.in_flight:
            return

        hit_normal = sum((c.hitNormal for c in data), Vector()) / len(data)
        hit_position = sum((c.hitPosition for c in data), Vector()) / len(data)

        if isinstance(target, bge_network.Pawn):
            momentum = self.mass * self.velocity.length * hit_normal

            bge_network.ActorDamagedSignal.invoke(self.owner.base_damage, self.owner.owner,
                                              hit_position, momentum,
                                              target=target)

            self.request_unregistration()

        elif self.in_flight:
            if other.name != self.object.name:
                self.object.setParent(other)

            self.lifespan = 5

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


class M4A1Attachment(bge_network.WeaponAttachment):

    entity_name = "M4"
