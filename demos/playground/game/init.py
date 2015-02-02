from network.world_info import WorldInfo
from network.enums import Netmodes

from game_system.timer import Timer

from .rules import Rules
from .replicables import *


__all__ = ["init_server", "init_client"]


def init_server():
    WorldInfo.netmode = Netmodes.server
    WorldInfo.rules = Rules()


def init_client():
    WorldInfo.netmode = Netmodes.client

    def func():
        from game_system.signals import ConnectToSignal
        ConnectToSignal.invoke("localhost", 1200)

    on_init = Timer(0.00, disposable=True)
    on_init.on_target = func