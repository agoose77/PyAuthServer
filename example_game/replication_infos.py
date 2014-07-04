from network.decorators import requires_netmode, simulated
from network.descriptors import Attribute
from network.type_flag import TypeFlag
from network.enums import Netmodes, Roles
from network.replicable import Replicable
from network.structures import TypedList, TypedSet
from network.world_info import WorldInfo

from game_system.controllers import PlayerControllerBase
from game_system.replication_infos import ReplicationInfo, PlayerReplicationInfo
from game_system.signals import BroadcastMessage

from game_system.resources import ResourceManager

from .enums import TeamRelation

__all__ = ["CTFPlayerReplicationInfo", "GameReplicationInfo",
           "TeamReplicationInfo", "RedTeam", "GreenTeam"]


class CTFPlayerReplicationInfo(PlayerReplicationInfo):

    team = Attribute(type_of=Replicable, complain=True)

    def conditions(self, is_owner, is_complain, is_initial):
        yield from super().conditions(is_owner, is_complain, is_initial)

        if is_complain:
            yield "team"


class GameReplicationInfo(ReplicationInfo):
    roles = Attribute(Roles(Roles.authority, Roles.simulated_proxy))

    time_to_start = Attribute(0.0)
    match_started = Attribute(False)
    players = Attribute(TypedList(Replicable), element_flag=TypeFlag(Replicable))

    @requires_netmode(Netmodes.server)
    @BroadcastMessage.global_listener
    def send_broadcast(self, message):
        player_controllers = WorldInfo.subclass_of(PlayerControllerBase)

        for controller in player_controllers:
            controller.receive_broadcast(message)

    def conditions(self, is_owner, is_complaint, is_initial):
        yield from super().conditions(is_owner, is_complaint, is_initial)

        yield "match_started"
        yield "time_to_start"
        yield "players"


class TeamReplicationInfo(ReplicationInfo):

    score = Attribute(0, complain=True)
    players = Attribute(TypedSet(Replicable), element_flag=TypeFlag(Replicable))

    @property
    def resources(self):
        return ResourceManager[self.__class__.__name__]

    @property
    def image_name(self):
        raise NotImplementedError()

    @simulated
    def get_relationship_with(self, team):
        return TeamRelation.friendly if team == self else TeamRelation.enemy

    def conditions(self, is_owner, is_complaint, is_initial):
        yield from super().conditions(is_owner, is_complaint, is_initial)

        if is_complaint:
            yield "score"

        yield "players"


class GreenTeam(TeamReplicationInfo):
    name = "Angus"

    @property
    def image_name(self):
        return "angus.tga"


class RedTeam(TeamReplicationInfo):
    name = "Josip"

    @property
    def image_name(self):
        return "josip.jpg"
