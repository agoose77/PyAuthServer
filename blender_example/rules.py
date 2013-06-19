from bge_network import PlayerController, Actor, PlayerLimitReached
from network import BaseRules, ConnectionStatus, Netmodes, Roles, ConnectionInterface
from operator import gt as greater_than

from actors import RPGController, Player

# Game Rules
class TeamDeathMatch(BaseRules):
    player_limit = 4
    
    @classmethod
    def pre_initialise(cls, addr, netmode):
        connections = ConnectionInterface.by_status(ConnectionStatus.handshake, greater_than)
        # Determine if too many players accepted 
        if connections >= cls.player_limit:
            raise PlayerLimitReached
        
    @classmethod
    def post_initialise(cls, conn):
        if conn.netmode == Netmodes.client: 
            # Create controller
            controller = RPGController()
            # Create pawn
            actor = Player()
            # Establish relationship
            controller.possess(actor) 
            return controller
        
    def on_disconnect(cls, replicable):
        return
    
    @classmethod
    def is_relevant(cls, conn, replicable):        
        # If it's a player controller (besides owning controllers)
        
        return True