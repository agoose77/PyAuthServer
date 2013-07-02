from collections import OrderedDict, namedtuple
from bge import logic, constraints
from .enums import Physics

class PlayerMove:
    def __init__(self, timestamp, deltatime, inputs):
        self.timestamp=timestamp
        self.deltatime=deltatime
        self.inputs=inputs
    
    def __iter__(self):
        return (self.timestamp, self.deltatime, self.inputs).__iter__()
            
class RenderState:
    def __init__(self, obj):
        self.obj = obj
        self.ignore = False
        self.save()
    
    def save(self):
        self.transform = self.obj.worldTransform.copy()
        self.angular = self.obj.worldAngularVelocity.copy()
        
        if self.obj.physics.mode == Physics.character:
            self.velocity = self.obj.character_controller.walkVelocity.copy()
            self.vertical_velocity = self.obj.character_controller.verticalVelocity
        else:
            self.velocity = self.obj.worldLinearVelocity.copy()
    
    def restore(self):
        self.obj.worldTransform = self.transform 
        if self.obj.physics.mode == Physics.character:
            self.obj.character_controller.walkVelocity = self.velocity
            self.obj.character_controller.verticalVelocity = self.vertical_velocity
        else:
            self.obj.worldLinearVelocity = self.velocity
            self.obj.worldAngularVelocity = self.angular 
     
    def __enter__(self):
        self.ignore = False
        self.save()
        
    def __exit__(self, *a, **k):
        if not self.ignore:
            self.restore()
            
class MoveManager:
    def __init__(self):
        self.saved_moves = OrderedDict()
        
        self.latest_move = 0
        self.max_id = 65535 
    
    def __bool__(self):
        return bool(self.saved_moves)
    
    def increment_move(self):
        self.latest_move += 1
        if self.latest_move > self.max_id:
            self.latest_move = 0
            
        return self.latest_move
    
    def add_move(self, move):
        move_id = self.increment_move()
        self.saved_moves[move_id] = move
    
    def get_move(self, move_id):
        return self.saved_moves[move_id]
    
    def remove_move(self, move_id):
        return self.saved_moves.pop(move_id)
        
    def sorted_moves(self, sort_filter=None):
        if callable(sort_filter):
            for k, v in self.saved_moves.items():
                if not sort_filter(k):
                    continue
                yield k, v
        else:
            yield from self.saved_moves.items()
    