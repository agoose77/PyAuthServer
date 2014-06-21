from bge_network.resources import ResourceManager

from network.replicable import Replicable
from network.decorators import simulated
from network.descriptors import Attribute, TypeFlag
from network.enums import Roles, Netmodes
from bge_network.actors import Actor
from game_system.signals import CollisionSignal
from game_system.enums import CollisionType

import aud


class ReplicatedAttributes(Replicable):

    my_name = Attribute(type_of=str)

    roles = Attribute(Roles(local=Roles.authority, remote=Roles.simulated_proxy))

    def conditions(self, is_owner, is_complain, is_initial):
        yield from super().conditions(is_owner, is_complain, is_initial)

        yield "my_name"


class ReplicatedNotifierAttributes(Replicable):

    my_name = Attribute(type_of=str, notify=True)

    roles = Attribute(Roles(local=Roles.authority, remote=Roles.simulated_proxy))

    def on_notify(self, name):
        print(name, "attribute has changed!")

    def conditions(self, is_owner, is_complain, is_initial):
        yield from super().conditions(is_owner, is_complain, is_initial)

        yield "my_name"


class ReplicatedFunctions(Replicable):

    roles = Attribute(Roles(local=Roles.authority, remote=Roles.simulated_proxy))

    @simulated
    def change_name(self, name: TypeFlag(str)) -> Netmodes.server:
        print(name, "is my new name!")


class Cube(Actor):

    entity_name = "Cube"

    roles = Attribute(Roles(local=Roles.authority, remote=Roles.simulated))

    def on_initialised(self):
        super().on_initialised()

        self.damage = 0
        self.max_damage = 100

    @simulated
    def play_sound(self):
        relative_file_path = self.resources["sounds"]["bump.mp3"]
        file_path = ResourceManager.from_relative_path(relative_file_path)

        factory = aud.Factory.file(file_path)
        device = aud.device()
        return device.play(factory)

    def handle_damage(self):
        self.damage += 20

        if self.damage >= self.max_damage:
            self.request_unregistration()

    @CollisionSignal.listener
    def on_collided(self, collision_result):
        if collision_result.collision_type == CollisionType.started:
            self.play_sound()
            self.handle_damage()