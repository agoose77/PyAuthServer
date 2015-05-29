from network.enums import Enumeration
from network.decorators import requires_netmode
from network.enums import Netmodes

from game_system.controllers import PlayerPawnController
from game_system.coordinates import Vector
from game_system.enums import ButtonState
from game_system.inputs import InputContext
from game_system.timer import Timer


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