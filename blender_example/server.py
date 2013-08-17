from bge_network import Network, BaseRules, WorldInfo, Netmodes, Pawn, PlayerController, AuthError
from cProfile import runctx

class TeamDeathMatchRules(BaseRules):
    relevant_radius_squared = 20 ** 2
    
    @classmethod
    def is_relevant(cls, player_controller, replicable):
        player_pawn = player_controller.pawn
        
        if isinstance(replicable, Pawn):
            rbs = replicable.rigid_body_state
            rbs2 = player_pawn.rigid_body_state
            return (rbs.position - rbs2.position).length_squared <= cls.relevant_radius_squared
    
    @classmethod
    def pre_initialise(cls, addr, netmode):
        if netmode == Netmodes.server:
            raise AuthError("Peer was not a client")
    
    @classmethod 
    def post_initialise(cls, conn):
        replicable = PlayerController()
        replicable.possess(Pawn())
        return replicable
    
WorldInfo.rules = TeamDeathMatchRules
WorldInfo.netmode = Netmodes.server

for i in range(100):
    Pawn()

network = Network("", 1200, update_interval=1/25)

def main():
    network.receive()
    Pawn.update_graph()
    network.send()