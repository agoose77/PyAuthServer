from collections import namedtuple, OrderedDict

from network.enums import Netmodes
from network.network import Network
from network.signals import DisconnectSignal
from network.world_info import WorldInfo

from .timer import Timer
from .tagged_delegate import EnvironmentDefinitionByTag


RewindState = namedtuple("RewindState", "position rotation animations")


class ServerGameLoop(EnvironmentDefinitionByTag):

    subclasses = {}


class ClientGameLoop(EnvironmentDefinitionByTag):

    subclasses = {}
