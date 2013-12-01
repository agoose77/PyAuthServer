import network


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
CustomSignal.invoke("Angus", target=my_printer)