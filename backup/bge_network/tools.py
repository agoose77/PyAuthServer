from collections import defaultdict, deque
from itertools import islice
from mathutils import Vector, Euler

def angular_from_quaternion(quaternion):
    angular = Vector(quaternion.to_euler())
    return angular

def quaternion_from_angular(angular):
    quat = Euler(angular).to_quaternion()
    return quat

class AttatchmentSocket:
    def __init__(self, parent, position):
        self.position = position
        self.parent = parent
        self.attatchment = None
        
    def attach(self, obj, align=False):
        obj.physics.position = self.parent.position + (self.parent.physics.orientation.to_matrix() * self.position)
        
        if align:
            obj.align_from(self.parent)
            
        self.attatchment = obj
        
        obj.setParent(self.parent)
        
    def detach(self):
        self.attatchment.removeParent()
        self.attatchment = None

class CircularBufferProperty:
    
    def __init__(self, size=3):
        self.parents = defaultdict(deque)
        self.size = size
    
    def __get__(self, parent, base=None):
        if parent is None:
            return self
        
        return self.parents[parent]
    
    def __set__(self, parent, value):
        values = self.parents[parent]
        values.append(value)
        
        if len(values) > self.size:
            values.popleft()

class AverageDifferenceProperty(CircularBufferProperty): 
    
    def mean(self, members):
        try:
            return sum(members) / len(members)
        except ZeroDivisionError:
            return 0.000
    
    def __get__(self, parent, base=None):
        if parent is None:
            return self
        
        values = super().__get__(parent)
        paired_values = zip(values, islice(values, 1, None))
        differences = [(b - a) for a, b in paired_values]
        return self.mean(differences)
    
class CircularAverageProperty(CircularBufferProperty):   
    
    def mean(self, members):
        try:
            return sum(members) / len(members)
        except ZeroDivisionError:
            return 0.000
    
    def __get__(self, parent, base=None):
        if parent is None:
            return self
        
        values = super().__get__(parent)
        
        return self.mean(values)
        