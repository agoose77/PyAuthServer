from network.enums import Netmodes, Roles
from network.network import create_network_manager
from network.world import World
from network.descriptors import Attribute
from network.rules import ReplicationRulesBase
from network.replicable import Replicable
from network.type_flag import TypeFlag
from network.scene import NetworkScene

from time import monotonic


class MyReplicable(Replicable):

    roles = Roles(Roles.authority, Roles.autonomous_proxy)
    name = Attribute("")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        print("INIT")

    def conditions(self, is_owner, is_complaint, is_initial):
        yield "name"

    def say(self, message: TypeFlag(str)) -> Netmodes.client:
        print("YO", message)


class Rules(ReplicationRulesBase):

    def __init__(self):
        self.scene = NetworkScene("BaseScene")

    def pre_initialise(self, address):
        print("Welcoming address", address)

    def post_initialise(self, replication_manager): #, replication_manager.associate_replicables
        with self.scene:
            player = MyReplicable()
            replication_manager.take_ownership(player)

        player.name = "Alex"
        player.say("HIYA BYUBBA")
        return player

    def post_disconnected(self, replication_manager, root_replicable):
        raise NotImplementedError

    def is_relevant(self, root_replicable, replicable):
        return True


world = World(Netmodes.server)
with world:
    network_manager = create_network_manager(world, port=1200)
    network_manager.rules = Rules()

    last_time = monotonic()
    accumulator = 0.0
    time_step = 1 / 60
    current_tick = 0

    update_frequency = 60
    update_interval = round(update_frequency * time_step)

    while True:
        now = monotonic()

        dt = now - last_time
        last_time = now

        accumulator += dt

        while accumulator >= time_step:
            accumulator -= time_step
            current_tick += 1

            network_manager.send(full_update=current_tick % update_interval)

            network_manager.receive()
