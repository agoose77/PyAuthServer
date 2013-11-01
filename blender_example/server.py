from bge_network import (WorldInfo, Netmodes, PlayerController, Controller, ReplicableInfo,
                         Actor, Pawn, Camera, AuthError, ServerGameLoop, AIController,
                         PlayerReplicationInfo, ReplicationRules, ConnectionStatus,
                         ConnectionInterface, BlacklistError, EmptyWeapon,
                         UpdateEvent, ActorDamagedEvent, ActorKilledEvent, Timer)
from functools import partial
from operator import gt as more_than
from weakref import proxy as weak_proxy

from events import ConsoleMessage
from matchmaker import BoundMatchmaker
from replicables import *
from random import randint


class TeamDeathMatch(ReplicationRules):

    countdown_running = False
    countdown_start = 0
    minimum_players_for_countdown = 0
    player_limit = 4

    ai_camera_class = Camera
    ai_controller_class = AIController
    ai_pawn_class = RobertNeville
    ai_replication_info_class = PlayerReplicationInfo
    ai_weapon_class = M4A1Weapon

    player_camera_class = Camera
    player_controller_class = LegendController
    player_pawn_class = RobertNeville
    player_replication_info_class = PlayerReplicationInfo
    player_weapon_class = M4A1Weapon

    relevant_radius_squared = 9 ** 2

    @property
    def players(self):
        return ConnectionInterface.by_status(
                 ConnectionStatus.disconnected,
                 more_than)

    @property
    def allow_countdown(self):
        return self.players >= self.minimum_players_for_countdown

    def allows_broadcast(self, sender, message):
        return len(message) <= 255

    def broadcast(self, sender, message):
        if not self.allows_broadcast(sender, message):
            return

        for replicable in WorldInfo.subclass_of(PlayerController):
            replicable.receive_broadcast(message)

    def create_new_ai(self, controller):
        pawn = self.ai_pawn_class()
        camera = self.ai_camera_class()
        weapon = self.ai_weapon_class()

        controller.possess(pawn)
        controller.set_camera(camera)
        controller.setup_weapon(weapon)

        pawn.position = Vector((randint(-10, 10), randint(-10, 10), 1))

    def create_new_player(self, controller):
        pawn = self.player_pawn_class()
        camera = self.player_camera_class()
        weapon = self.player_weapon_class()

        controller.possess(pawn)
        controller.set_camera(camera)
        controller.setup_weapon(weapon)

        pawn.position = Vector((4, 4, 1))

    def stop_countdown(self):
        self.reset_countdown()
        self.countdown_running = False

    def is_relevant(self, player_controller, replicable):
        # We never allow PlayerController classes
        if isinstance(replicable, Controller):
            return False

        if replicable.always_relevant:
            return True

        # Check by distance, then frustum checks
        if isinstance(replicable, Actor) and (replicable.visible or \
                                              replicable.always_relevant):
            player_pawn = player_controller.pawn

            in_range = player_pawn and (replicable.position - \
                    player_pawn.position).length_squared <= \
                    self.relevant_radius_squared

            player_camera = player_controller.camera

            if in_range or (player_controller.camera and \
                            player_camera.sees_actor(replicable)):
                return True

        if isinstance(replicable, Weapon):
            return False

        if isinstance(replicable, WeaponAttachment):
            return True

    @ActorKilledEvent.global_listener
    def killed(self, attacker, target):
        message = "{} was killed by {}'s {}".format(target.owner, attacker,
                                                attacker.pawn)

        self.broadcast(attacker, message)

        target.owner.unpossess()
        target.request_unregistration()
        target.owner.weapon.unpossessed()
        target.owner.weapon.request_unregistration()

        if isinstance(target.owner, self.player_controller_class):
            self.create_new_player(target.owner)

        else:
            self.create_new_ai(target.owner)

    def on_initialised(self, **da):
        super().on_initialised()

        self.info = GameReplicationInfo(register=True)
        self.matchmaker = BoundMatchmaker("http://www.coldcinder.co.uk/"\
                                     "networking/matchmaker")

        self.matchmaker_updater = Timer(initial_value=10,
                                            count_down=True,
                                            on_target=self.update_matchmaker,
                                            repeat=True)

        self.black_list = []

        self.matchmaker.register_server("Demo Server", "Test Map",
                                        self.player_limit, 0)

    def on_disconnect(self, replicable):
        self.broadcast(replicable, "{} disconnected".format(replicable))

    def post_initialise(self, connection):
        controller = self.player_controller_class()
        player_info = self.player_replication_info_class()

        controller.info = player_info
        self.create_new_player(controller)

        return controller

    def pre_initialise(self, address_tuple, netmode):
        if netmode == Netmodes.server:
            raise AuthError("Peer was not a client")

        if self.players >= self.player_limit:
            raise AuthError("Player limit reached")

        ip_address, port = address_tuple

        if ip_address in self.black_list:
            raise BlacklistError()

    def reset_countdown(self):
        self.info.time_to_start = float(self.countdown_start)

    def start_countdown(self):
        self.reset_countdown()
        self.countdown_running = True

    def start_match(self):
        self.info.match_started = True

    @ActorDamagedEvent.global_listener
    def on_damaged(self, damage, instigator, hit_position, momentum, target):
        if not isinstance(target, Pawn):
            return

        if not target.health:
            ActorKilledEvent.invoke(instigator, target=target)

    @UpdateEvent.global_listener
    def update(self, delta_time):
        info = self.info

        if self.countdown_running:
            info.time_to_start = max(0.0, info.time_to_start - delta_time)

            # If countdown stops, start match
            if not info.time_to_start:
                self.stop_countdown()
                self.start_match()

        elif self.allow_countdown and not info.match_started:
            self.start_countdown()

    def update_matchmaker(self):
        self.matchmaker.update_server("Test Map", self.player_limit,
                                    self.players)

class Server(ServerGameLoop):

    def create_network(self):
        network = super().create_network()
        WorldInfo.rules = TeamDeathMatch(register=True)
        return network
