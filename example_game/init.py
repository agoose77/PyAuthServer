from network.world_info import WorldInfo
from network.enums import Netmodes

from .client_ui import FPSSystem
from .replication_rules import TeamDeathMatch

__all__ = ["init_server", "init_client"]


def init_server():
    WorldInfo.netmode = Netmodes.server
    WorldInfo.rules = TeamDeathMatch(register_immediately=True)


def init_client():
    WorldInfo.ui = FPSSystem() # Global reference to persist
    WorldInfo.netmode = Netmodes.client
