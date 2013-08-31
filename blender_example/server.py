from bge_network import WorldInfo, Netmodes, ReplicableInfo, Actor, Pawn, Camera, AuthError, ServerLoop, PlayerReplicationInfo, BaseGameInfo, ConnectionStatus, ConnectionInterface, InstanceNotifier
from operator import gt as more_than
from weakref import proxy as weak_proxy
from functools import partial

from actors import *
    
class TeamDeathMatch(BaseGameInfo):
    
    relevant_radius_squared = 3 ** 2
    countdown_running = False
    
    countdown_start = 0
    
    player_controller_class = ExampleController
    player_replication_info_class = PlayerReplicationInfo
    player_pawn_class = Pawn
    player_camera_class = Camera
    
    def on_registered(self):
        super().on_registered()
        
        self.info = GameReplicationInfo(register=True)
    
    def is_relevant(self, player_controller, replicable):
        player_pawn = player_controller.pawn
        player_camera = player_controller.camera
        
        if isinstance(replicable, PlayerController):
            return False
        
        if isinstance(replicable, ReplicableInfo):
            return True

        if isinstance(replicable, Actor) and (replicable.visible or replicable.always_relevant):
            in_range = player_pawn and (replicable.position - player_pawn.position).length_squared <= self.relevant_radius_squared
            
            in_camera = (player_camera and player_camera.sees_actor(replicable))
        
            if (in_range or in_camera):
                return True
            
    def pre_initialise(self, addr, netmode):
        if netmode == Netmodes.server:
            raise AuthError("Peer was not a client")
        
    def create_new_player(self, controller, callback_data=None):
        pawn = self.player_pawn_class()
        camera = self.player_camera_class()
        
        controller.possess(pawn)
        controller.set_camera(camera)
        
        pawn.position = Vector()
    
    def killed(self, killer, killed, killed_pawn):
        pass
    
    def end_countdown(self, aborted=True):
        self.reset_countdown()
        self.countdown_running = False
        
        if aborted:
            return
        
        self.start_match()
    
    def reset_countdown(self):
        self.info.time_to_start = float(self.countdown_start)
    
    def start_countdown(self):
        self.reset_countdown()
        self.countdown_running = True
    
    def get_player_count(self):
        return ConnectionInterface.by_status(ConnectionStatus.disconnected, more_than)
    
    def can_start_countdown(self):
        player_count = self.get_player_count()
        return player_count > 0
    
    def start_match(self):
        for controller in WorldInfo.subclass_of(ExampleController):
            self.create_new_player(controller)
        for i in range(20):
            Pawn()
        self.info.match_started = True
    
    def post_initialise(self, connection):
        controller = self.player_controller_class()
        player_info = self.player_replication_info_class()
        
        controller.info = player_info
        
        if self.info.match_started:
            self.create_new_player(controller)
        
        return controller
    
    def update(self, delta_time):
            
        if self.countdown_running:
            self.info.time_to_start = max(0.0, self.info.time_to_start - delta_time)
            
            if not self.info.time_to_start:
                self.end_countdown(False)
                
        elif self.can_start_countdown() and not self.info.match_started:
            self.start_countdown()
            
class Server(ServerLoop, InstanceNotifier):            
    
    def create_network(self):
        network = super().create_network()
        
        WorldInfo.game_info = TeamDeathMatch(register=True)
        
        return network