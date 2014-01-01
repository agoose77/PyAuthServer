from replicables import *

import bge_network
import functools
import operator
import weakref

import signals
import matchmaker
import random

import stats_ui


class TeamDeathMatch(bge_network.ReplicationRules):

    countdown_running = False
    countdown_start = 0
    minimum_players_for_countdown = 0
    player_limit = 4

    ai_camera_class = bge_network.Camera
    ai_controller_class = EnemyController
    ai_pawn_class = Zombie
    ai_replication_info_class = bge_network.AIReplicationInfo
    ai_weapon_class = ZombieWeapon

    player_camera_class = bge_network.Camera
    player_controller_class = LegendController
    player_pawn_class = RobertNeville
    player_replication_info_class = bge_network.PlayerReplicationInfo
    player_weapon_class = M4A1Weapon

    relevant_radius_squared = 9 ** 2

    @property
    def players(self):
        return bge_network.ConnectionInterface.by_status(
                 bge_network.ConnectionStatus.disconnected,
                 operator.gt)

    @property
    def allow_countdown(self):
        return self.players >= self.minimum_players_for_countdown

    def allows_broadcast(self, sender, message):
        return len(message) <= 255

    def broadcast(self, sender, message):
        if not self.allows_broadcast(sender, message):
            return

        for replicable in bge_network.WorldInfo.subclass_of(
                                                bge_network.PlayerController):
            replicable.receive_broadcast(message)

    def create_new_ai(self, controller=None):
        '''This function can be called without a controller,
        in which case it establishes one.
        Used to respawn AI character pawns
        @param controller: options, controller instance'''
        if controller is None:
            controller = self.ai_controller_class()
            controller.info = self.ai_replication_info_class()

        pawn = self.ai_pawn_class()
        camera = self.ai_camera_class()
        weapon = self.ai_weapon_class()

        controller.possess(pawn)
        controller.set_camera(camera)
        controller.setup_weapon(weapon)

        pawn.position = Vector((random.randint(-10, 10),
                                random.randint(-10, 10), 3))
        return controller

    def create_new_player(self, controller=None):
        '''This function can be called without a controller,
        in which case it establishes one.
        Used to respawn player character pawns
        @param controller: options, controller instance'''
        if controller is None:
            controller = self.player_controller_class()
            controller.info = self.player_replication_info_class()

        pawn = self.player_pawn_class()
        camera = self.player_camera_class()
        weapon = self.player_weapon_class()

        controller.possess(pawn)
        controller.set_camera(camera)
        controller.setup_weapon(weapon)

        pawn.position = Vector((4, 4, 2))
        return controller

    def is_relevant(self, player_controller, replicable):
        if replicable.always_relevant:
            return True

        # Check by distance, then frustum checks
        if isinstance(replicable, bge_network.Actor) and replicable.visible:
            player_pawn = player_controller.pawn

            in_range = player_pawn and (replicable.position - \
                    player_pawn.position).length_squared <= \
                    self.relevant_radius_squared

            player_camera = player_controller.camera

            if in_range or (player_camera and \
                            player_camera.sees_actor(replicable)):
                return True

        # These classes are not permitted (unless owned by client)
        if isinstance(replicable, (bge_network.Controller,
                                   bge_network.Weapon)):
            return False

        return False

    @bge_network.ActorKilledSignal.global_listener
    def killed(self, attacker, target):
        message = "{} was killed by {}'s {}".format(target.owner, attacker,
                                                attacker.pawn)

        self.broadcast(attacker, message)

        target.owner.unpossess()
        target.request_unregistration()

        if target.owner.weapon:
            target.owner.weapon.unpossessed()
            target.owner.weapon.request_unregistration()

        if isinstance(target.owner, self.player_controller_class):
            self.create_new_player(target.owner)

        else:
            self.create_new_ai(target.owner)

    def on_initialised(self, **da):
        super().on_initialised()

        self.info = GameReplicationInfo(register=True)
        self.matchmaker = matchmaker.BoundMatchmaker(
                         "http://www.coldcinder.co.uk/networking/matchmaker"
                         )
        self.matchmaker_timer = bge_network.Timer(initial_value=10,
                                            count_down=True,
                                            on_target=self.update_matchmaker,
                                            repeat=True)
        self.black_list = []

        self.matchmaker.register("Demo Server", "Test Map",
                                        self.player_limit, 0)

    def on_disconnect(self, replicable):
        self.broadcast(replicable, "{} disconnected".format(replicable))

    def post_initialise(self, connection):
        return self.create_new_player()

    def pre_initialise(self, address_tuple, netmode):
        if netmode == bge_network.Netmodes.server:
            raise bge_network.AuthError("Peer was not a client")

        if self.players >= self.player_limit:
            raise bge_network.AuthError("Player limit reached")

        ip_address, port = address_tuple

        if ip_address in self.black_list:
            raise bge_network.BlacklistError()

    def reset_countdown(self):
        self.info.time_to_start = float(self.countdown_start)

    def start_countdown(self):
        self.reset_countdown()
        self.countdown_running = True

    def start_match(self):
        self.info.match_started = True

    def stop_countdown(self):
        self.reset_countdown()
        self.countdown_running = False

    @bge_network.UpdateSignal.global_listener
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
        self.matchmaker.poll("Test Map", self.player_limit,
                                    self.players)

    def on_unregistered(self):
        super().on_unregistered()


class Server(bge_network.ServerGameLoop):

    def create_network(self):
        network = super().create_network()

        bge_network.WorldInfo.rules = TeamDeathMatch(register=True)
        return network
