import bge_network
from behaviours import *
from bge import logic

import signals
import aud
import controls
import mathutils


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


class LegendController(bge_network.PlayerController):

    input_fields = "forward", "backwards", "left", "right", "shoot", "run", "voice"

    def on_notify(self, name):
        super().on_notify(name)

        if name == "weapon":
            signals.UIWeaponChangedSignal.invoke(self.weapon)
            signals.UIUpdateSignal.invoke("ammo", self.weapon.ammo)

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

        if self.inputs.shoot:
            self.start_fire()

        # Only record when we need to
        if self.inputs.voice != self.microphone.active:
            self.microphone.active = self.inputs.voice

        if self.weapon:
            signals.UIUpdateSignal.invoke("ammo", self.weapon.ammo)


class RobertNeville(bge_network.Pawn):
    entity_name = "Suzanne_Physics"

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


class M4A1Weapon(bge_network.Weapon):

    def on_initialised(self):
        super().on_initialised()

        self.max_ammo = 50
        self.attachment_class = M4A1Attachment
        self.shoot_interval = 0.1
        self.theme_colour = [0.53, 0.94, 0.28, 1.0]
        self.shot_type = bge_network.ShotType.projectile

    def projectile_shot(self):
        projectile = SphereProjectile()
        projectile.position = self.owner.pawn.position + self.owner.pawn.rotation.to_matrix().col[1] * 3 + Vector((0, 0, 1))
        projectile.rotation = self.owner.pawn.rotation.copy()
        projectile.velocity = mathutils.Vector((0, 15, 2))


class ZombieAttachment(bge_network.WeaponAttachment):

    entity_name = "EmptyWeapon"

    @simulated
    def play_fire_effects(self):
        self.owner.play_animation("Attack", 0, 60)


class SphereProjectile(bge_network.Projectile):
    entity_name = "Sphere"

    def on_initialised(self):
        self.lifespan = 10

        super().on_initialised()

    @bge_network.CollisionSignal.listener
    def on_collision(self, other, is_new, data):
        self.request_unregistration()


class ZombieWeapon(bge_network.Weapon):

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
