class BaseRules:
    '''Base class for game rules'''
    
    @classmethod
    def pre_initialise(cls, addr, netmode):
        return NotImplemented
        
    @classmethod
    def post_initialise(cls, conn):
        return NotImplemented
    
    @classmethod
    def on_disconnect(cls, replicable):
        return NotImplemented
    
    @classmethod
    def is_relevant(cls, conn, replicable):        
        return NotImplemented
    