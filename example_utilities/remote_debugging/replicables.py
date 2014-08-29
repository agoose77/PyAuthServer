from network.replicable import Replicable
from network.descriptors import Attribute
from network.type_flag import TypeFlag
from network.enums import Netmodes, Roles

from traceback import print_exc

from .tools import stdout_io


class RemoteTerminal(Replicable):
    roles = Attribute(Roles(Roles.authority, Roles.autonomous_proxy))

    def on_initialised(self):
        super().on_initialised()

        self.data = {}
        self.data.update(globals())

    def execute(self, command: TypeFlag(str, max_length=1000)) -> Netmodes.server:
        with stdout_io() as s:
            try:
                exec(command, self.data)

            except Exception:
                print_exc()

        self.result(s.getvalue())

    def result(self, result: TypeFlag(str, max_length=1000)) -> Netmodes.client:
        print(result)