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

    def execute(self, command, on_received):
        self.on_received = on_received
        self.server_execute(command)

    def server_execute(self, command: TypeFlag(str, max_length=1000)) -> Netmodes.server:
        with stdout_io() as s:
            try:
                # Create a code object in order to print result
                code = compile(command, "<dummy>", "single")
                exec(code, self.data)

            except Exception:
                print_exc()

        result = s.getvalue()[:-1]
        self.result(result)

    def result(self, result: TypeFlag(str, max_length=1000)) -> Netmodes.client:
        print(result)
        self.on_received()