from operator import gt as greater_than
from random import choice

from network.connection_interfaces import ConnectionInterface
from network.enums import ConnectionStatus
from network.replication_rules import ReplicationRulesBase
from network.signals import ConnectionDeletedSignal, ConnectionSuccessSignal

from game_system.controllers import PlayerController
from game_system.errors import AuthError, BlacklistError
from game_system.signals import PawnKilledSignal
from game_system.timer import Timer

from game_system.entities import *
from bge_game_system.gameloop import ServerGameLoop

from .actors import *
from .controllers import *
from .matchmaker import BoundMatchmaker
from .replication_infos import *
from .signals import TeamSelectionQuerySignal
from .weapons import BowWeapon


class TeamDeathMatch(ReplicationRulesBase):

    countdown_running = False
    countdown_start = 0
    minimum_players_for_countdown = 0
    player_limit = 4
    relevant_radius_squared = 80 ** 2

    # AI Classes
    ai_camera_class = Camera
    ai_controller_class = EnemyController
    ai_pawn_class = CTFPawn
    ai_replication_info_class = CTFPlayerReplicationInfo
    ai_weapon_class = BowWeapon

    # Player Classes
    player_camera_class = Camera
    player_controller_class = CTFPlayerController
    player_pawn_class = CTFPawn
    player_replication_info_class = CTFPlayerReplicationInfo
    player_weapon_class = BowWeapon

    @property
    def connected_players(self):
        disconnected_status = ConnectionStatus.pending
        return ConnectionInterface.by_status(disconnected_status, greater_than)

    def allows_broadcast(self, sender, message):
        return True

    @TeamSelectionQuerySignal.global_listener
    def assign_team(self, player_controller, team):
        self.setup_player_pawn(player_controller)

        team.players.add(player_controller.info)
        player_controller.info.team = team
        player_controller.team_changed(team)

    def broadcast(self, sender, message):
        if not self.allows_broadcast(sender, message):
            return

        for replicable in WorldInfo.subclass_of(PlayerController):
            replicable.receive_broadcast(message)

    def setup_fake_teams(self):
        """Spawn teams for game mode"""
        # Create teams
        team_green = GreenTeam()
        team_red = RedTeam()

    def is_relevant(self, player_controller, replicable):
        """Determine whether a network object is relevant to a client controller

        :param player_controller: client's player controller
        :param replicable: replicable to test
        :rtype: bool
        """
        if replicable.always_relevant:
            return True

        # If a visible actor
        if isinstance(replicable, Actor) and replicable.visible:
            player_pawn = player_controller.pawn

            if player_pawn:

                # First check by distance
                position_difference = replicable.world_position - player_pawn.world_position
                in_range = position_difference.length_squared <= self.relevant_radius_squared

                if in_range:
                    return True

                # Otherwise by camera frustum
                player_camera = player_controller.camera
                if player_camera and player_camera.sees_actor(replicable):
                    return True

        return False

    @PawnKilledSignal.global_listener
    def killed(self, attacker, target):
        message = "{} was killed by {}".format(target.owner, attacker)

        self.broadcast(attacker, message)

        if isinstance(target.owner, self.player_controller_class):
            self.setup_player_pawn(target.owner)

        else:
            self.setup_ai_pawn(target.owner)

    def on_initialised(self):
        super().on_initialised()

        self.info = GameReplicationInfo(register=True)

        self.matchmaker = BoundMatchmaker("http://www.coldcinder.co.uk/networking/matchmaker")
        self.matchmaker.register("Demo Server", "Test Map", self.player_limit, 0)

        self.matchmaker_timer = Timer(start=10, count_down=True, repeat=True)
        self.matchmaker_timer.on_target = self.update_matchmaker

        self.countdown_timer = Timer(end=self.countdown_start, active=False)
        self.countdown_timer.on_target = self.start_match

        self.black_list = []
        self.setup_fake_teams()

    @ConnectionDeletedSignal.global_listener
    def on_disconnect(self, replicable):
        self.broadcast(replicable, "{} disconnected".format(replicable))

        self.update_matchmaker()

    def post_initialise(self, connection):
        """Initialisation callback for valid connections

        :param connection: connection for client
        """
        # Create player controller for player
        controller = self.player_controller_class(register=True)
        controller.info = self.player_replication_info_class(register=True)

        return controller

    def pre_initialise(self, address_tuple, netmode):
        """Validation callback for new connections

        :param address_tuple: tuple of address, port of incoming data
        :param netmode: :py:code:`network.enums.Netmodes` enum value of client
        """
        if netmode == Netmodes.server:
            raise AuthError("Peer was not a client")

        if self.connected_players >= self.player_limit:
            raise AuthError("Player limit reached")

        ip_address, port = address_tuple

        if ip_address in self.black_list:
            raise BlacklistError("Player has been blacklisted")

    def start_match(self):
        self.info.match_started = True

    def setup_ai_pawn(self, controller):
        """This function can be called without a controller,
        in which case it establishes one.
        Used to respawn AI character pawns

        :param controller: options, controller instance"""
        controller.forget_pawn()

        pawn = self.ai_pawn_class()
        weapon = self.ai_weapon_class()
        camera = self.ai_camera_class()

        controller.possess(pawn)
        controller.set_camera(camera)
        controller.set_weapon(weapon)

        pawn.world_position = choice(WorldInfo.subclass_of(SpawnPoint)).world_position
        return controller

    def setup_player_pawn(self, controller):
        """This function can be called without a controller,
        in which case it establishes one.
        Used to respawn player character pawns

        :param controller: options, controller instance"""
        controller.forget_pawn()

        pawn = self.player_pawn_class(register=True)
        weapon = self.player_weapon_class(register=True)
        camera = self.player_camera_class(register=True)

        controller.possess(pawn)
        controller.set_camera(camera)
        controller.set_weapon(weapon)

        pawn.world_position = choice(WorldInfo.subclass_of(SpawnPoint)).world_position
        return controller

    @LogicUpdateSignal.global_listener
    def update(self, delta_time):
        players_needed = self.minimum_players_for_countdown
        countdown_running = self.countdown_timer.active

        if not (countdown_running or self.info.match_started) and self.connected_players >= players_needed:
            self.countdown_timer.reset()

    @ConnectionSuccessSignal.global_listener
    def update_matchmaker(self):
        self.matchmaker.poll("Test Map", self.player_limit, self.connected_players)


class Server(ServerGameLoop):

    def create_network(self):
        network = super().create_network()

        WorldInfo.rules = TeamDeathMatch(register=True)
        return network
