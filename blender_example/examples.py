import bge_network
import aud
from bge import logic

"""
class CustomSignal(network.Signal):
    pass


class Printer(network.Replicable):

    my_name = network.Attribute(type_of=str, complain=True, notify=True)
    my_name2 = network.Attribute(type_of=str, complain=True)
    my_name3 = network.Attribute(type_of=str, complain=True)

    roles = network.Attribute(network.Roles(
                                    local=network.Roles.authority, 
                                    remote=network.Roles.simulated_proxy
                                            )
                              )

    def on_notify(self, name):
        print(name, "has changed")

    def conditions(self, is_owner, is_complain, is_initial):
        yield from super().conditions(is_owner, is_complain, is_initial)

        if is_complain:
            yield "my_name"
            yield "my_name2"
            yield "my_name3"

    @CustomSignal.global_listener
    @network.simulated
    def change_name(self, name: network.StaticValue(str)) -> network.Netmodes.server:
        self.my_name = name

my_printer = Printer()

my_printer.change_name("Angus")
CustomSignal.invoke("Angus", target=my_printer)"""


class Cube(bge_network.Actor):

    entity_name = "Cube"

    roles = bge_network.Attribute(bge_network.Roles(
                                            local=bge_network.Roles.authority,
                                            remote=bge_network.Roles.simulated,
                                                    )
                                  )

    def on_initialised(self):
        super().on_initialised()

        self.damage = 0
        self.max_damage = 100

    @bge_network.simulated
    def play_sound(self):
        file_path = logic.expandPath("//bump.mp3")
        factory = aud.Factory.file(file_path)
        device = aud.device()
        handle = device.play(factory)

    def handle_damage(self, is_collision):
        self.damage -= 20

        if self.damage <= self.max_damage:
            self.destroy()

    @bge_network.CollisionSignal.listener
    def on_collided(self, target, is_collision):
        if is_collision:
            self.play_sound()
            self.handle_damage()