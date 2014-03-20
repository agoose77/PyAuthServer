import bge_network

__all__ = ['TeamRelation']


class TeamRelation(metaclass=bge_network.Enum):
    values = ["friendly", "enemy", "neutral"]
