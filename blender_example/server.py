from bge_network import WorldInfo, Netmodes, Pawn, AuthError, ServerLoop, PlayerReplicationInfo, BaseGameInfo, ConnectionStatus, ConnectionInterface, Attribute, Roles, Replicable, InstanceNotifier
from operator import gt as more_than
from weakref import proxy as weak_proxy

from actors import *
    
class TeamDeathMatch(BaseGameInfo, InstanceNotifier):
    
    relevant_radius_squared = 20 ** 2
    countdown_running = False
    
    countdown_start = 5
    
    player_controller_class = ExampleController
    player_replication_info_class = PlayerReplicationInfo
    player_pawn_class = Pawn
    
    def on_registered(self):
        super().on_registered()
        
        self.info = GameReplicationInfo(register=True)

        self.pending_ownership = {}

        Replicable.subscribe(self)
    
    def notify_registration(self, replicable):
        # Possess and transform
        if replicable in self.pending_ownership:
            controller, position = self.pending_ownership.pop(replicable)
            controller.possess(replicable)
            replicable.position = position
    
    def is_relevant(self, player_controller, replicable):
        player_pawn = player_controller.pawn
        
        if isinstance(replicable, GameReplicationInfo):
            return True
        
        if isinstance(replicable, Pawn):
            return (replicable.position - player_pawn.position).length_squared <= self.relevant_radius_squared
    
    def pre_initialise(self, addr, netmode):
        if netmode == Netmodes.server:
            raise AuthError("Peer was not a client")
    
    def spawn_default_pawn_for(self, controller, point):
        pawn = self.player_pawn_class()
        self.pending_ownership[pawn] = controller, point
    
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
        return player_count > 1
    
    def start_match(self):
        for controller in WorldInfo.subclass_of(ExampleController):
            self.spawn_default_pawn_for(controller, Vector())
        
        self.info.match_started = True
    
    def post_initialise(self, conn):
        replicable = self.player_controller_class()
        player_info = self.player_replication_info_class()
        
        replicable.info = player_info
        
        return replicable
    
    def update(self, delta_time):
            
        if self.countdown_running:
            self.info.time_to_start = max(0.0, self.info.time_to_start - delta_time)
            
            if not self.info.time_to_start:
                self.end_countdown(False)
                
        elif self.can_start_countdown() and not self.info.match_started:
            self.start_countdown()
            
class Server(ServerLoop):
    
    def create_network(self):
        network = super().create_network()
        
        WorldInfo.game_info = TeamDeathMatch(register=True)
        
        return network