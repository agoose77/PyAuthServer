from network.enums import Enumeration
from network.decorators import requires_netmode
from network.enums import Netmodes

from game_system.ai.sensors import SightSensor
from game_system.ai.state_machine.fsm import FiniteStateMachine
from game_system.ai.state_machine.state import State
from game_system.controllers import PlayerPawnController, AIPawnController
from game_system.coordinates import Vector
from game_system.entities import Navmesh
from game_system.enums import ButtonState
from game_system.inputs import InputContext
from game_system.timer import Timer

from .planner import *


class JumpState(Enumeration):
    values = ""


class TestPandaPlayerController(PlayerPawnController):
    input_context = InputContext(buttons=["left", "right", "up", "down", "jump", "shoot"])

    def on_initialised(self):
        super().on_initialised()

        self.jump_cooldown = Timer(0.3, active=False)

    @requires_netmode(Netmodes.server)
    def shoot(self):
        from .actors import RocketBomb
        cube = RocketBomb()
        cube.launch_from(self)
        cube.transform.world_position = self.pawn.transform.world_position + Vector((0, 0, 4))

    def process_inputs(self, buttons, ranges):
        pawn = self.pawn
        if pawn is None:
            return

        y_speed = 15
        x_speed = 8
        turn_speed = 3
        jump_speed = 5

        angular = Vector()

        if pawn.on_ground:
            velocity = Vector()
            velocity.z = self.pawn.physics.world_velocity.z

            if buttons['jump'] == ButtonState.pressed and not self.jump_cooldown.active:
                velocity.z += jump_speed

                self.jump_cooldown.reset()

            if buttons['up'] in {ButtonState.pressed, ButtonState.held}:
                velocity.y += y_speed

            if buttons['down'] in {ButtonState.pressed, ButtonState.held}:
                velocity.y -= y_speed

            # Convert velocity to world space
            velocity.rotate(pawn.transform.world_orientation)
            pawn.physics.world_velocity = velocity

        if buttons['right'] in {ButtonState.pressed, ButtonState.held}:
            angular.z -= turn_speed

        if buttons['left'] in {ButtonState.pressed, ButtonState.held}:
            angular.z += turn_speed

        if buttons['shoot'] == ButtonState.pressed:
            self.shoot()

        pawn.physics.world_angular = angular


class GOTOState(State):

    def __init__(self, controller):
        super().__init__("GOTO")

        self.controller = controller
        self.request = None

        self.waypoint_margin = 0.5
        self.target_margin = 2

        self._path_node = None

    def find_path_to(self, source, target):
        navmesh = next(iter(Replicable.subclass_of_type(Navmesh)))
        return navmesh.navmesh.find_path(source, target)

    def draw_path(self, current_position, path):
        from panda3d.core import LineSegs, Vec4, Vec3
        path = [Vec3(*v) for v in path]

        segments = LineSegs()
        segments.set_thickness(2.0)
        segments.set_color((1, 1, 0, 1))
        segments.move_to(current_position)

        for point in path:
            segments.draw_to(point)

        if self._path_node:
            self._path_node.remove_node()

        node = segments.create()
        self._path_node = render.attach_new_node(node)

    def update(self):
        request = self.request

        if request is None:
            return

        if request.status != EvaluationState.running:
            return

        # We need a pawn to perform GOTO action
        pawn = self.controller.pawn
        if pawn is None:
            return

        pawn_position = pawn.transform.world_position
        target_position = request.target.transform.world_position

        try:
            path = request._path

        except AttributeError:
            request._path = path = self.find_path_to(pawn_position, target_position)

        self.draw_path(pawn_position[:], path)

        target_distance = (target_position - pawn_position).length

        while path:
            waypoint_position = path[0]
            to_waypoint = waypoint_position - pawn_position

            # Update request
            distance = to_waypoint.xy.length
            request.distance_to_target = distance

            if distance < self.waypoint_margin:
                path[:] = path[1:]

            else:
                pawn.physics.world_velocity = to_waypoint.normalized() * pawn.walk_speed

                if target_distance > self.target_margin:
                    return
                break

        request.status = EvaluationState.success
        pawn.physics.world_velocity = to_waypoint * 0


class TestAIController(AIPawnController):
    actions = [GetNearestAmmoPickup()]
    goals = [FindAmmoGoal()]

    def on_initialised(self):
        super().on_initialised()

        self.fsm = FiniteStateMachine()
        self.fsm.add_state(GOTOState(self))

        self.blackboard['has_ammo'] = False
        self.blackboard['ammo'] = 0

        view_sensor = SightSensor()
        self.sensor_manager.add_sensor(view_sensor)

        interpreter = PickupInterpreter()
        view_sensor.add_interpreter(interpreter)