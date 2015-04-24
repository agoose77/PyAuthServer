from network.descriptors import TypeFlag
from network.rpc import Pointer
from network.decorators import requires_netmode
from network.enums import Netmodes
from network.world_info import WorldInfo

from game_system.controllers import PlayerPawnController
from game_system.coordinates import Vector
from game_system.enums import ButtonState
from game_system.inputs import InputContext

from .actors import TestActor


class TestPandaPlayerController(PlayerPawnController):
    input_context = InputContext(buttons=["left", "right", "up", "down", "debug"])

    debug = False

    @requires_netmode(Netmodes.server)
    def shoot(self):
        cube = TestActor()
        pawn = self.pawn
        cube.transform.world_position = pawn.transform.world_position + Vector((-5, 0, 0))

    def process_inputs(self, buttons, ranges):
        if buttons['debug'] == ButtonState.pressed:
            self.shoot()
            #self.debug = not self.debug

        if self.debug:
            self.shoot()
            # print(self.buffer)
            # print(buttons)

        y_sign = 0
        if buttons['up'] in {ButtonState.pressed, ButtonState.held}:
            y_sign += 1

        if buttons['down'] in {ButtonState.pressed, ButtonState.held}:
            y_sign -= 1

        x_sign = 0
        if buttons['right'] in {ButtonState.pressed, ButtonState.held}:
            x_sign -= 1

        if buttons['left'] in {ButtonState.pressed, ButtonState.held}:
            x_sign += 1

        y_speed = y_sign * 2.0
        rotation_speed = x_sign

        pawn = self.pawn

        velocity = Vector((0.0, y_speed, 0.0))
        try:
            velocity.rotate(pawn.transform.world_orientation)
        except AttributeError:
            base.invoke_exit()

        angular = Vector((0.0, 0.0, rotation_speed))

        pawn.physics.world_angular = angular
        pawn.physics.world_velocity = velocity