from network.replicable import Replicable
from network.descriptors import Attribute
from network.decorators import requires_netmode
from network.enums import Netmodes

from game_system.controllers import PlayerController
from game_system.coordinates import Vector
from game_system.entities import Actor, Pawn
from game_system.replication_info import PlayerReplicationInfo
from game_system.inputs import InputManager
from game_system.enums import InputEvents, ListenerType


class PlaygroundPRI(PlayerReplicationInfo):
    pass


class PlaygroundPlayerController(PlayerController):

    pass


class Projectile(Actor):
    pass


class PlaygroundPawn(Pawn):
    component_tags = [c for c in Pawn.component_tags if not "animation" in c]

    def on_initialised(self):
        super().on_initialised()

        InputManager.add_listener(InputEvents.SPACEKEY, ListenerType.action_in, self.spawn_projectile)

    def spawn_projectile(self) -> Netmodes.server:
        direction = Vector((0, 1,  2))
        speed = 15
        velocity = Vector((0, speed, 0))

        projectile = Projectile()
        projectile.physics.world_velocity = velocity
        print(projectile.physics.world_velocity)
        projectile.transform.align_to(direction)