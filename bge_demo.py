from network.enums import Netmodes
from network.network import NetworkManager

from bge import logic
from bge_game_system.world import World

from game_system.fixed_timestep import FixedTimeStepManager
import demos.v2.entities



def on_step(delta_time):
    network_manager.receive()
    world.tick()

    is_network_tick = not world.current_tick % 3
    network_manager.send(is_network_tick)

    logic.NextFrame()


world = World(Netmodes.client)
network_manager = NetworkManager(world, "localhost", 0)
network_manager.connect_to("localhost", 1200)

loop = FixedTimeStepManager()
loop.on_step = on_step
loop.run()
