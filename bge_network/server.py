from bge import logic, events, render; import sys; sys.path.append(logic.expandPath("//../"))

from network import WorldInfo, BaseRules, Netmodes, Roles, ConnectionStatus 

from errors import *
from actors import *
from enums import *

from game import Game, random_spawn

import attributes
import operator

# Add random actors
random_spawn(20)
    
# Game Rules
class TeamDeathMatch(BaseRules):
    player_limit = 4
    
    @classmethod
    def pre_initialise(cls, netmode):
        connections = game.connections_by_status(ConnectionStatus.handshake, operator.gt)
        if connections >= cls.player_limit:
            raise PlayerLimitReached
        
    @classmethod
    def post_initialise(cls, conn):
        if conn.netmode == Netmodes.client: 
            # Create controller
            controller = PlayerController()
            
            # Create pawn
            actor = Actor()
            # Establish relationship
            controller.possess(actor) 
        
            return controller
        
    def on_disconnect(cls, replicable):
        return
    
    @classmethod
    def is_relevant(cls, conn, replicable):
        # If no network role
        if replicable.remote_role is Roles.none:
            return False
        
        # If it's a player controller (besides owning controllers)
        elif isinstance(replicable, PlayerController):
            return False
        
        return True

game = Game(addr="127.0.0.1", port=1200)

# Set network mode
WorldInfo.netmode = Netmodes.server
WorldInfo.rules = TeamDeathMatch

def main(cont):  
    try:
        game.update()    
    except QuitGame:
        logic.endGame()  
    