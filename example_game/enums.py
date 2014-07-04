from network.enums import Enumeration

__all__ = ['TeamRelation']


class TeamRelation(metaclass=Enumeration):
    values = ["friendly", "enemy", "neutral"]

