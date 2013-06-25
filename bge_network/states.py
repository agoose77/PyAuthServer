from collections import OrderedDict, namedtuple
from bge import logic, constraints
from .enums import Physics

PlayerMove = namedtuple("PlayerMove", ("timestamp", "deltatime", "inputs"))
            
class RenderState:
    def __init__(self, obj):
        self.obj = obj
        self.ignore = False
        self.save()
    
    def save(self):
        self.transform = self.obj.worldTransform.copy()
        self.angular = self.obj.worldAngularVelocity.copy()
        if self.obj.physics.mode == Physics.character:
            self.velocity = constraints.getCharacter(self.obj).walkDirection.copy()
        else:
            self.velocity = self.obj.worldLinearVelocity 
    
    def restore(self):
        self.obj.worldTransform = self.transform 
        if self.obj.physics.mode == Physics.character:
            constraints.getCharacter(self.obj).walkDirection = self.velocity
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
        self.to_correct = OrderedDict()
        
        self.latest_move = 0
        self.latest_correction = 0
        self.max_id = 65535 
    
    def __bool__(self):
        return bool(self.saved_moves) or bool(self.to_correct)
    
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
        self.saved_moves.pop(move_id)
        
    def sorted_moves(self, sort_filter=None):
        if callable(sort_filter):
            for k, v in self.saved_moves.items():
                if not sort_filter(k):
                    continue
                yield k, v
        else:
            yield from self.saved_moves.items()
    