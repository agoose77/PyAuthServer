from bge_network import BaseRules, WorldInfo, Netmodes, Pawn, PlayerController, AuthError, ServerLoop

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
        replicable.pawn.skeleton_name = "Suzanne_Skeleton"
        return replicable
    

class Server(ServerLoop):
    
    def create_network(self):
        network = super().create_network()
        
        WorldInfo.rules = TeamDeathMatchRules
        return network