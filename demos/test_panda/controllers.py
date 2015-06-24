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
        self.target_margin = 2.5

        self._path_node = None

    def _draw_path(self, current_position, path):
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

        # If target is invalid
        target = request.target
        if not target:
            # Cleanup any navigation queries
            if hasattr(request, "_query"):
                query = request._query
                self.controller.navigation_manager.remove_query(query)

            self.request = None
            return

        pawn_position = pawn.transform.world_position
        target_position = request.target.transform.world_position

        try:
            query = request._query

        except AttributeError:
            query = self.controller.navigation_manager.create_query(request.target)
            query.replan_if_invalid = True
            request._query = query

        path = query.path
        if path is None:
            return

        points = path.points
        target_distance = (target_position.xy - pawn_position.xy).length

        # Render the path
        self._draw_path(pawn_position[:], points)

        while points:
            waypoint_position = points[0]

            to_waypoint = (waypoint_position - pawn_position)
            to_waypoint.z = 0.0

            # Update request
            distance = to_waypoint.length
            request.distance_to_target = distance

            # If we have nearly reached the waypoint
            if distance < self.waypoint_margin:
                points[:] = points[1:]

            else:
                pawn.physics.world_velocity = to_waypoint.normalized() * pawn.walk_speed
                pawn.physics.world_angular = Vector()
                pawn.transform.align_to(to_waypoint)

                # We're done!
                if target_distance < self.target_margin:
                    request.status = EvaluationState.success
                    pawn.physics.world_velocity = to_waypoint * 0

                return


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