from network.rules import ReplicationRulesBase

from game_system.entities import Actor

from .replicables import *

__all__ = "Rules",


class Rules(ReplicationRulesBase):
    """Game rules for playground demo"""

    def pre_initialise(self, addr, netmode):
        return

    def post_initialise(self, replication_stream):
        from game_system .resources import ResourceManager

        pc = PlaygroundPlayerController(register_immediately=True)
        pc.info = PlaygroundPRI(register_immediately=True)
        pawn = PlaygroundPawn(register_immediately=True)
        pc.possess(pawn)
        return pc

    def is_relevant(self, conn, replicable):
        return isinstance(replicable, Actor) or isinstance(replicable, PlayerReplicationInfo)