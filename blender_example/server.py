from bge_network import BaseRules, WorldInfo, Netmodes, Pawn, AuthError, ServerLoop, PlayerReplicationInfo

from actors import ExampleController

class TeamDeathMatchRules(BaseRules):
    relevant_radius_squared = 20 ** 2
    
    @classmethod
    def is_relevant(cls, player_controller, replicable):
        player_pawn = player_controller.pawn
        
        if isinstance(replicable, Pawn):
            return (replicable.position - player_pawn.position).length_squared <= cls.relevant_radius_squared
    
    @classmethod
    def pre_initialise(cls, addr, netmode):
        if netmode == Netmodes.server:
            raise AuthError("Peer was not a client")
    
    @classmethod 
    def post_initialise(cls, conn):
        replicable = ExampleController()
        player_pawn = Pawn()
        player_info = PlayerReplicationInfo()
        
        replicable.possess(player_pawn)
        replicable.info = player_info
        
        # Not registered yet so this is allowed
        #replicable.pawn.skeleton_name = "Suzanne_Skeleton"
        
        return replicable
    
class Server(ServerLoop):
    
    def create_network(self):
        network = super().create_network()
        
        WorldInfo.rules = TeamDeathMatchRules
        return network