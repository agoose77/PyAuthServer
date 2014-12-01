from collections import namedtuple

from .tagged_delegate import EnvironmentDefinitionByTag


RewindState = namedtuple("RewindState", "position rotation animations")


class ServerGameLoop(EnvironmentDefinitionByTag):

    subclasses = {}


class ClientGameLoop(EnvironmentDefinitionByTag):

    subclasses = {}
