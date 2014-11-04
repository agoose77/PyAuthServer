from network.enums import Enumeration

__all__ = ['TeamRelation']


class TeamRelation(Enumeration):
    values = ["friendly", "enemy", "neutral"]

