import bge_network
from behaviours import *

import signals
import controls


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

    input_fields = "forward", "backwards", "left", "right", "shoot", "run"

    def receive_broadcast(self, message_string:
                          bge_network.StaticValue(str)) ->  bge_network.Netmodes.client:
        signals.ConsoleMessage.invoke(message_string)

    def on_initialised(self):
        super().on_initialised()

        behaviour = SequenceNode(
                                 controls.camera_control(),
                                 controls.inputs_control()
                                 )

        behaviour.should_restart = True
        self.behaviour.root.add_child(behaviour)


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

        self.walk_speed = 2.7
        self.run_speed = 6


class M4A1Weapon(bge_network.Weapon):

    def on_initialised(self):
        super().on_initialised()

        self.sound_path = "sounds"
        self.max_ammo = 50
        self.attachment_class = M4A1Attachment
        self.shoot_interval = 1


class ZombieAttachment(bge_network.WeaponAttachment):

    entity_name = "EmptyWeapon"

    def __init__(self, *a, **k):
        super().__init__(*a, **k)

    @simulated
    def play_fire_effects(self):
        self.owner.play_animation("Attack", 0, 60)


class ZombieWeapon(bge_network.Weapon):

    def on_initialised(self):
        super().on_initialised()

        self.sound_path = "sounds"
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
