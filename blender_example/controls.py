from bge_network import *
from mathutils import Vector, Euler
from math import radians, sin, cos, copysign

from .behaviours import *


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
    play_state = SequenceNode(GetPawn(), HasInputs(), HandleInputs())

    return play_state


class HasInputs(ConditionNode):

    def condition(self, blackboard):
        return "inputs" in blackboard


class HasMouse(ConditionNode):

    def condition(self, blackboard):
        return "mouse" in blackboard


class HandleMouseYaw(LeafNode):

    def evaluate(self, blackboard):
        mouse_diff_x, *_ = blackboard['mouse']
        pawn = blackboard['pawn']

        pawn.angular = Vector((0, 0, mouse_diff_x * 20 * pawn.turn_speed))
        return EvaluationState.success


class IsThirdPerson(ConditionNode):

    def condition(self, blackboard):
        camera = blackboard['camera']
        return camera.mode == CameraMode.third_person


class HandleFirstPersonCamera(LeafNode):

    def evaluate(self, blackboard):
        mouse_diff_x, mouse_diff_y = blackboard['mouse']
        pawn = blackboard['pawn']
        camera = blackboard['camera']

        look_speed = 2
        look_limit = radians(45)

        delta_yaw = mouse_diff_x * look_speed
        delta_pitch = mouse_diff_y * look_speed

        current_pitch = camera.local_rotation[0]

        if (current_pitch < look_limit and delta_pitch > 0):
            if delta_pitch > (look_limit - current_pitch):
                delta_pitch = (look_limit - current_pitch)

        elif (current_pitch > -look_limit and delta_pitch < 0):
            if delta_pitch < (-look_limit - current_pitch):
                delta_pitch = (-look_limit - current_pitch)

        else:
            return EvaluationState.success

        current_pitch += delta_pitch

        # Set pawn's Z rotation
        pawn_rotation = pawn.rotation.copy()
        pawn_rotation.rotate(Euler((0, 0, delta_yaw)))

        # Set camera's X rotation
        camera.local_rotation = Euler((current_pitch, 0, 0))

        # Set replication rotation
        pawn.view_pitch = current_pitch

        return EvaluationState.success


class HandleThirdPersonCamera(LeafNode):

    def evaluate(self, blackboard):
        _, mouse_diff_y = blackboard['mouse']
        pawn = blackboard['pawn']
        camera = blackboard['camera']

        look_speed = 1
        look_limit = radians(45)

        rotation_delta = mouse_diff_y * look_speed
        pawn.view_pitch = 0.0
        camera.local_position.rotate(Euler((rotation_delta, 0, 0)))

        minimum_y = -camera.gimbal_offset
        maximum_y = cos(look_limit) * -camera.gimbal_offset

        minimum_z = 0
        maximum_z = sin(look_limit) * camera.gimbal_offset

        camera.local_position.y = min(maximum_y, max(minimum_y,
                                            camera.local_position.y))
        camera.local_position.z = min(maximum_z, max(minimum_z,
                                            camera.local_position.z))

        camera.local_position.length = camera.gimbal_offset

        rotation = Vector((0, -1, 0)).rotation_difference(
                          camera.local_position).inverted().to_euler()
        rotation[0] *= -1

        camera.local_rotation = rotation

        return EvaluationState.success


class HandleInputs(LeafNode):

    def evaluate(self, blackboard):
        inputs = blackboard['inputs']
        pawn = blackboard['pawn']
        controller = blackboard['controller']

        y_plane = inputs.forward - inputs.backwards
        x_plane = inputs.right - inputs.left

        movement_mode = MovementState.run if inputs.run else MovementState.walk
        if movement_mode == MovementState.walk:
            forward_speed = pawn.walk_speed

        elif movement_mode == MovementState.run:
            forward_speed = pawn.run_speed

        if inputs.shoot:
            controller.start_fire()

        if pawn.on_ground:
            velocity = Vector((x_plane, y_plane, 0.0))
            velocity.length = forward_speed

            if inputs.jump:
                velocity.z = pawn.walk_speed

            pawn.velocity = velocity

        return EvaluationState.success
