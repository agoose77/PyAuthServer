from bge_network import *
from mathutils import Vector, Euler
from math import radians, sin, cos

from behaviours import *


def camera_control():
    play_state = SequenceNode(
                              GetPawn(),
                              GetCamera(),
                              HasMouse(),
                              HandleMouseYaw(),
                              SelectorNode(
                                           SequenceNode(
                                                        IsThirdPerson(),
                                                        HandleThirdPersonCamera()
                                                        ),
                                           HandleFirstPersonCamera()
                                           )
                              )

    return play_state


def inputs_control():
    play_state = SequenceNode(
                              GetPawn(),
                              HasInputs(),
                              HandleInputs()
                              )

    return play_state


class HasInputs(ConditionNode):

    def condition(self, blackboard):
        return "inputs" in blackboard


class HasMouse(ConditionNode):

    def condition(self, blackboard):
        return "mouse" in blackboard


class HandleMouseYaw(SignalLeafNode):

    def evaluate(self, blackboard):
        mouse_diff_x, *_ = blackboard['mouse']
        pawn = blackboard['pawn']

        pawn.angular = Vector((0, 0, mouse_diff_x * 20 * pawn.turn_speed))
        return EvaluationState.success


class IsThirdPerson(ConditionNode):

    def condition(self, blackboard):
        camera = blackboard['camera']
        return camera.mode == CameraMode.third_person


class HandleFirstPersonCamera(SignalLeafNode):

    def evaluate(self, blackboard):
        _, mouse_diff_y = blackboard['mouse']
        pawn = blackboard['pawn']
        camera = blackboard['camera']

        look_speed = 1
        look_limit = radians(45)

        rotation_delta = mouse_diff_y * look_speed

        new_pitch = pawn.view_pitch + rotation_delta
        new_pitch = max(0.0, min(look_limit, new_pitch))

        pawn.view_pitch = new_pitch
        camera.rotation = Euler((new_pitch, 0, 0))
        return EvaluationState.success


class HandleThirdPersonCamera(SignalLeafNode):

    def evaluate(self, blackboard):
        _, mouse_diff_y = blackboard['mouse']
        pawn = blackboard['pawn']
        camera = blackboard['camera']

        look_speed = 1
        look_limit = radians(45)

        rotation_delta = mouse_diff_y * look_speed
        pawn.view_pitch = 0.0
        camera.local_position.rotate(Euler((rotation_delta, 0, 0)))

        minimum_y = -camera.offset
        maximum_y = cos(look_limit) * -camera.offset

        minimum_z = 0
        maximum_z = sin(look_limit) * camera.offset

        camera.local_position.y = min(maximum_y, max(minimum_y,
                                            camera.local_position.y))
        camera.local_position.z = min(maximum_z, max(minimum_z,
                                            camera.local_position.z))

        camera.local_position.length = camera.offset

        rotation = Vector((0, -1, 0)).rotation_difference(
                          camera.local_position).inverted().to_euler()
        rotation[0] *= -1
        rotation.rotate(Euler((radians(90), 0, 0)))

        camera.local_rotation = rotation

        return EvaluationState.success


class HandleInputs(SignalLeafNode):

    def evaluate(self, blackboard):
        inputs = blackboard['inputs']
        pawn = blackboard['pawn']

        y_plane = inputs.forward - inputs.backwards
        x_plane = inputs.right - inputs.left

        movement_mode = MovementState.run if inputs.run \
                                else MovementState.walk
        if movement_mode == MovementState.walk:
            forward_speed = pawn.walk_speed

        elif movement_mode == MovementState.run:
            forward_speed = pawn.run_speed

        velocity = Vector((x_plane, y_plane, 0.0))
        velocity.length = forward_speed

        pawn.velocity.xy = velocity.xy

        return EvaluationState.success
