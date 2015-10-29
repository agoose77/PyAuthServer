from network.world import World
from network.enums import Netmodes
from network.network import NetworkManager

from bge import logic
from bge_game_system.entity import EntityBuilder
from bge_game_system.input import InputManager

from game_system.physics import NetworkPhysicsManager
from game_system.entity import Entity, Actor
from game_system.main_loop import FixedTimeStepManager

import demos.v2.entities


class BGESceneController:

    def __init__(self, scene, input_manager):
        self._scene = scene
        self._bge_scene = next(s for s in logic.getSceneList() if s.name == scene.name)

        self._entity_builder = EntityBuilder(self._bge_scene, input_manager)
        self._physics_world = NetworkPhysicsManager()

        scene.messenger.add_subscriber("replicable_created", self.on_replicable_created)

    def on_replicable_created(self, replicable):
        print("LOAD1")
        if isinstance(replicable, Entity):
            self._entity_builder.load_entity(replicable)
            print("LOAD")

            if isinstance(replicable, Actor):


class BGEGameloop(FixedTimeStepManager):

    def __init__(self, world, network_manager):
        super().__init__()

        self._world = world
        self._network_manager = network_manager
        self._input_manager = InputManager()

        self._scene_controllers = {}

        world.messenger.add_subscriber("scene_added", self.on_scene_added)
        world.messenger.add_subscriber("scene_removed", self.on_scene_removed)

        self._current_tick = 0
        self._network_tick_rate = 20
        self._network_interval = round(1 / (self._network_tick_rate * self.time_step))

    def on_scene_added(self, scene):
        self._scene_controllers[scene] = BGESceneController(scene, self._input_manager)

    def on_scene_removed(self, scene):
        self._scene_controllers.pop(scene)

    def on_step(self, delta_time):
        self._input_manager.update()

        self._network_manager.receive()
        self._world.tick()

        is_network_tick = not self._current_tick % self._network_interval
        self._network_manager.send(is_network_tick)

        logic.NextFrame()

        self._current_tick += 1


world = World(Netmodes.client)
network_manager = NetworkManager(world, "localhost", 0)
network_manager.connect_to("localhost", 1200)

game = BGEGameloop(world, network_manager)
game.delegate()