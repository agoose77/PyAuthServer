from bge_network import (PlayerController, ReplicableInfo,
                         Attribute, Roles, Pawn,
                         Weapon, WeaponAttachment, CameraMode,
                         MovementState, Netmodes, StaticValue,
                         WorldInfo, AIController, simulated, UpdateSignal)
from mathutils import Vector, Euler
from math import radians, cos, sin
from signals import ConsoleMessage

from behaviours import *
from controls import camera_control, inputs_control


class GameReplicationInfo(ReplicableInfo):
    roles = Attribute(Roles(Roles.authority, Roles.simulated_proxy))

    time_to_start = Attribute(0.0)
    match_started = Attribute(False)

    def conditions(self, is_owner, is_complaint, is_initial):
        yield from super().conditions(is_owner, is_complaint, is_initial)

        yield "match_started"
        yield "time_to_start"


class EnemyController(AIController):

    def on_initialised(self):
        super().on_initialised()

        behaviour = SelectorNode(
                                 dying_behaviour(),
                                 attack_behaviour(),
                                 idle_behaviour()
                                 )

        behaviour.should_restart = True
        self.behaviour.root.add_child(behaviour)


class LegendController(PlayerController):

    input_fields = "forward", "backwards", "left", "right", "shoot", "run"

    def receive_broadcast(self, message_string:
                          StaticValue(str)) ->  Netmodes.client:
        ConsoleMessage.invoke(message_string)

    def on_initialised(self):
        super().on_initialised()

        behaviour = SequenceNode(
                                 camera_control(),
                                 inputs_control()
                                 )

        behaviour.should_restart = True
        self.behaviour.root.add_child(behaviour)


class RobertNeville(Pawn):
    entity_name = "Suzanne_Physics"

    def on_initialised(self):
        super().on_initialised()

        self.walk_speed = 3
        self.run_speed = 6


class Zombie(Pawn):

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


class M4A1Weapon(Weapon):

    def on_initialised(self):
        super().on_initialised()

        self.sound_path = "sounds"
        self.max_ammo = 50
        self.attachment_class = M4A1Attachment
        self.shoot_interval = 1


class ZombieWeapon(Weapon):

    def on_initialised(self):
        super().on_initialised()

        self.sound_path = "sounds"
        self.max_ammo = 1

        self.shoot_interval = 1
        self.maximum_range = 8
        self.effective_range = 6
        self.base_damage = 80

    def consume_ammo(self):
        pass


class M4A1Attachment(WeaponAttachment):

    entity_name = "M4"
