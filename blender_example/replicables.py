from bge_network import (PlayerController, ReplicableInfo,
                         Attribute, Roles, Pawn,
                         Weapon, WeaponAttachment, CameraMode,
                         MovementState, Netmodes, StaticValue,
                         WorldInfo, AIController, simulated, UpdateSignal)
from mathutils import Vector, Euler
from math import radians, cos, sin
from signals import ConsoleMessage

from behaviours import *
from bge_network.behaviour_tree import *


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
                                attack_behaviour(),
                                idle_behaviour()
                                )
        behaviour.should_restart = True

        self.behaviour.root.add_child(behaviour)

    @simulated
    @ActorKilledSignal.listener
    def killed(self):
        self.behaviour.reset()


class LegendController(PlayerController):

    input_fields = "forward", "backwards", "left", "right", "shoot", "run"

    near_zero = 0.001

    def receive_broadcast(self, message_string:
                          StaticValue(str)) ->  Netmodes.client:
        ConsoleMessage.invoke(message_string)

    def on_initialised(self):
        super().on_initialised()

        self.mouse_sensitivity = 20

    def mouse_turn(self, mouse_diff_x, delta_time):
        self.pawn.angular = Vector((0, 0, mouse_diff_x * \
                        self.mouse_sensitivity * self.pawn.turn_speed))

    def mouse_pitch(self, mouse_diff_y, delta_time):
        look_speed = 1
        look_limit = radians(45)
        look_mode = self.camera_mode

        rotation_delta = mouse_diff_y * look_speed

        if look_mode == CameraMode.first_person:
            new_pitch = self.pawn.view_pitch + rotation_delta
            new_pitch = max(0.0, min(look_limit, new_pitch))

            self.pawn.view_pitch = new_pitch
            self.camera.rotation = Euler((new_pitch, 0, 0))

        elif look_mode == CameraMode.third_person:
            self.pawn.view_pitch = 0.0
            self.camera.local_position.rotate(Euler((rotation_delta, 0, 0)))

            minimum_y = -self.camera_offset
            maximum_y = cos(look_limit) * -self.camera_offset

            minimum_z = 0
            maximum_z = sin(look_limit) * self.camera_offset

            self.camera.local_position.y = min(maximum_y, max(minimum_y,
                                                self.camera.local_position.y))
            self.camera.local_position.z = min(maximum_z, max(minimum_z,
                                                self.camera.local_position.z))

            self.camera.local_position.length = self.camera_offset

            rotation = Vector((0, -1, 0)).rotation_difference(
                              self.camera.local_position).inverted().to_euler()
            rotation[0] *= -1
            rotation.rotate(Euler((radians(90), 0, 0)))

            self.camera.local_rotation = rotation

    def handle_inputs(self, state, inputs, mouse_diff_x,
                     mouse_diff_y, delta_time):

        if abs(mouse_diff_x) < self.near_zero:
            mouse_diff_x = self.near_zero / 1000
        if abs(mouse_diff_y) < self.near_zero:
            mouse_diff_y = self.near_zero / 1000

        self.mouse_turn(mouse_diff_x, delta_time)
        self.mouse_pitch(mouse_diff_y, delta_time)

        y_plane = inputs.forward - inputs.backwards
        x_plane = inputs.right - inputs.left

        movement_mode = MovementState.run if inputs.run \
                                else MovementState.walk
        if movement_mode == MovementState.walk:
            forward_speed = self.pawn.walk_speed
        elif movement_mode == MovementState.run:
            forward_speed = self.pawn.run_speed

        velocity = Vector((x_plane, y_plane, 0.0))
        velocity.length = forward_speed

        self.pawn.velocity.xy = velocity.xy


class RobertNeville(Pawn):
    entity_name = "Suzanne_Physics"

    def on_initialised(self):
        super().on_initialised()

        self.walk_speed = 3
        self.run_speed = 6


class Zombie(Pawn):

    entity_name = "Zombie"


class M4A1Weapon(Weapon):

    def on_initialised(self):
        super().on_initialised()

        self.sound_path = "sounds"
        self.max_ammo = 50
        self.attachment_class = M4A1Attachment
        self.shoot_interval = 1


class M4A1Attachment(WeaponAttachment):

    entity_name = "M4"
