from network.decorators import requires_netmode, simulated
from network.descriptors import Attribute, TypeFlag, MarkAttribute
from network.enums import Netmodes, Roles
from network.replicable import Replicable
from network.structures import TypedList, TypedSet
from network.world_info import WorldInfo

from bge_network.controllers import PlayerController
from bge_network.replication_infos import ReplicationInfo, PlayerReplicationInfo
from bge_network.signals import BroadcastMessage

from .enums import TeamRelation

__all__ = ["CTFPlayerReplicationInfo", "GameReplicationInfo", "TeamReplicationInfo"]


class CTFPlayerReplicationInfo(PlayerReplicationInfo):

    team = Attribute(type_of=Replicable, complain=True)

    def conditions(self, is_owner, is_complain, is_initial):
        yield from super().conditions(is_owner, is_complain, is_initial)

        if is_complain:
            yield "team"


class GameReplicationInfo(ReplicationInfo):
    roles = Attribute(
                      Roles(
                            Roles.authority,
                            Roles.simulated_proxy
                            )
                      )

    time_to_start = Attribute(0.0)
    match_started = Attribute(False)
    players = Attribute(TypedList(Replicable),
                        element_flag=TypeFlag(Replicable))

    @requires_netmode(Netmodes.server)
    @BroadcastMessage.global_listener
    def send_broadcast(self, message):
        player_controllers = WorldInfo.subclass_of(PlayerController)

        for controller in player_controllers:
            controller.receive_broadcast(message)

    def conditions(self, is_owner, is_complaint, is_initial):
        yield from super().conditions(is_owner, is_complaint, is_initial)

        yield "match_started"
        yield "time_to_start"
        yield "players"


class TeamReplicationInfo(ReplicationInfo):

    name = Attribute(type_of=str, complain=True)
    score = Attribute(0, complain=True)
    players = Attribute(TypedSet(Replicable),
                        element_flag=TypeFlag(Replicable))

    @simulated
    def get_relationship_with(self, team):
        return(TeamRelation.friendly if team == self else TeamRelation.enemy)

    def conditions(self, is_owner, is_complaint, is_initial):
        yield from super().conditions(is_owner, is_complaint, is_initial)

        if is_complaint:
            yield "name"
            yield "score"

        yield "players"
