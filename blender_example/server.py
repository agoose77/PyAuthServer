from actors import *
from bge_network import (WorldInfo, Netmodes, PlayerController, Controller, ReplicableInfo,
                         Actor, Pawn, Camera, AuthError, ServerLoop, AIController,
                         PlayerReplicationInfo, ReplicationRules, ConnectionStatus,
                         ConnectionInterface, InstanceNotifier, BlacklistError, EmptyWeapon,
                         UpdateEvent, ActorDamagedEvent)
from functools import partial
from operator import gt as more_than
from weakref import proxy as weak_proxy


class TeamDeathMatch(ReplicationRules):

    countdown_running = False
    countdown_start = 0
    minimum_players_for_countdown = 0

    ai_count = 1

    ai_controller_class = AIController
    ai_camera_class = Camera
    ai_pawn_class = RobertNeville
    ai_replication_info_class = PlayerReplicationInfo
    ai_weapon_class = M4A1Weapon

    player_camera_class = Camera
    player_controller_class = LegendController
    player_pawn_class = RobertNeville
    player_replication_info_class = PlayerReplicationInfo
    player_weapon_class = M4A1Weapon

    relevant_radius_squared = 9 ** 2

    def allows_broadcast(self, sender, message):
        return len(message) <= 255

    def broadcast(self, sender, message):
        if not self.allows_broadcast(sender, message):
            return

        for replicable in WorldInfo.subclass_of(PlayerController):

            replicable.receive_broadcast(sender, message)

    def can_start_countdown(self):
        player_count = self.get_player_count()
        return player_count >= self.minimum_players_for_countdown

    def create_new_ai(self, controller, callback_data=None):
        pawn = self.ai_pawn_class()
        camera = self.ai_camera_class()
        weapon = self.ai_weapon_class()
        pawn.object['i'] = "ai"
        controller.possess(pawn)
        controller.set_camera(camera)
        controller.setup_weapon(weapon)

        pawn.position = Vector((1, 4, 0))

    def create_new_player(self, controller, callback_data=None):
        pawn = self.player_pawn_class()
        camera = self.player_camera_class()
        weapon = self.player_weapon_class()

        pawn.object['i'] = "lcl"
        controller.possess(pawn)
        controller.set_camera(camera)
        controller.setup_weapon(weapon)

        pawn.position = Vector((4, 4, 1))

    def create_ai_controllers(self):
        for i in range(self.ai_count):
            self.ai_controller_class()

    def end_countdown(self, aborted=True):
        self.reset_countdown()
        self.countdown_running = False

        if aborted:
            return

        self.start_match()

    def get_player_count(self):
        return ConnectionInterface.by_status(ConnectionStatus.disconnected,
                                             more_than)

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

    def killed(self, killer, killed, killed_pawn):
        pass

    def on_initialised(self, **da):
        super().on_initialised()

        self.info = GameReplicationInfo(register=True)
        self.black_list = []

        self.create_ai_controllers()

    def post_initialise(self, connection):
        controller = self.player_controller_class()
        player_info = self.player_replication_info_class()

        controller.info = player_info

        if self.info.match_started:
            self.create_new_player(controller)

        return controller

    def pre_initialise(self, addr, netmode):

        if netmode == Netmodes.server:
            raise AuthError("Peer was not a client")

        ip, port = addr

        if ip in self.black_list:
            raise BlacklistError()

    def reset_countdown(self):
        self.info.time_to_start = float(self.countdown_start)

    def start_countdown(self):
        self.reset_countdown()
        self.countdown_running = True

    def start_match(self):
        for controller in WorldInfo.subclass_of(PlayerController):
            self.create_new_player(controller)
        for controller in WorldInfo.subclass_of(AIController):
            self.create_new_ai(controller)

        self.info.match_started = True

    @ActorDamagedEvent.listener(True)
    def on_damaged(self, damage, instigator, hit_position, momentum, target):
        if not target.health:
            print("{} died!".format(target))

    @UpdateEvent.listener(True)
    def update(self, delta_time):

        if self.countdown_running:
            self.info.time_to_start = max(0.0,
                          self.info.time_to_start - delta_time)

            if not self.info.time_to_start:
                self.end_countdown(False)

        elif self.can_start_countdown() and not self.info.match_started:
            self.start_countdown()


class Server(ServerLoop, InstanceNotifier):

    def create_ui(self):
        return None

    def create_network(self):
        network = super().create_network()

        WorldInfo.rules = TeamDeathMatch(register=True)

        return network
