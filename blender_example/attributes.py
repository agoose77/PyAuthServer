from network import WorldInfo, Replicable, Float8, Float4, UInt8, String, register_handler, register_description
from mathutils import Vector, Euler
from itertools import chain

    
class AnimationData:
    __slots__ = "name", "end_frame", "timestamp", "start_frame", "mode"
    
    def __init__(self, name, end_frame, mode, start_frame=0):
        self.name = name
        self.mode = mode
        self.timestamp = 0.000 
        self.end_frame = end_frame
        self.start_frame = start_frame
    
    def __description__(self):
        return hash((self.mode, self.name, self.start_frame, self.end_frame, self.timestamp))
        
class PhysicsData:
    __slots__ = "mode", "timestamp", "position", "velocity"
    
    def __init__(self, mode, position=None, velocity=None):
        self.mode = mode
        self.timestamp = 0.000
        self.position = Vector() if position is None else position
        self.velocity = Vector() if velocity is None else velocity
    
    @property
    def moving(self):
        return bool(self.velocity.length)
    
    def __description__(self):
        return hash(tuple(chain(self.position, self.velocity, (self.mode,))))
    
class Vector8:
    @classmethod
    def pack(cls, vect):
        pack = Float8.pack
        return b''.join(pack(c) for c in vect)
    
    @classmethod
    def unpack(cls, bytes_):
        packer_size = Float8.size()
        unpack = Float8.unpack
        return Vector((unpack(bytes_[i * packer_size: (i + 1) * packer_size]) for i in range(3)))
    
    @classmethod
    def unpack_merge(cls, vect, bytes_):
        packer_size = Float8.size()
        unpack = Float8.unpack
        vect[:] = (unpack(bytes_[i * packer_size: (i + 1) * packer_size]) for i in range(3))
        
    @classmethod
    def size(cls, bytes_=None):
        return Float8.size() * 3
        
    unpack_from = unpack

Vector4 = type("Vector4", (Vector8,), {"packer": Float4})

class AnimationHandler:
    @classmethod
    def pack(cls, anim):
        data = UInt8.pack(anim.mode), UInt8.pack(anim.start_frame), UInt8.pack(anim.end_frame), String.pack(anim.name), Float8.pack(anim.timestamp) 
        return b''.join(data)
    
    @classmethod
    def unpack(cls, bytes_):
        record = AnimationData(mode=UInt8.unpack_from(bytes_), 
               start_frame=UInt8.unpack_from(bytes_[1:]),
               end_frame=UInt8.unpack_from(bytes_[2:]),
               name=String.unpack_from(bytes_[3:]))
        
        record.timestamp = Float8.unpack_from(bytes_[3 + String.size(bytes_[3:]):])
        return record
    
    @classmethod
    def unpack_merge(cls, anim, bytes_):
        anim.mode = UInt8.unpack_from(bytes_)
        anim.start_frame = UInt8.unpack_from(bytes_[1:])
        anim.end_frame = UInt8.unpack_from(bytes_[2:])
        anim.name = String.unpack_from(bytes_[3:])
        anim.timestamp = Float8.unpack_from(bytes_[3+String.size(bytes_[3:]): ])
    
    unpack_from = unpack
    
    @classmethod
    def size(cls, bytes_=None):
        initial = 3 
        return initial + String.size(bytes_[initial:]) + Float8.size()
    
class PhysicsHandler:
    @classmethod
    def pack(cls, phys):
        data = UInt8.pack(phys.mode), Float8.pack(phys.timestamp), Vector8.pack(phys.position), Vector8.pack(phys.velocity)
        return b''.join(data)
        
    @classmethod
    def unpack(cls, bytes_):
        phys = PhysicsData(bytes_[0])
        bytes_ = bytes_[1:]
        phys.timestamp = Float8.unpack_from(bytes_)
        bytes_ = bytes_[Float8.size():]
        phys.position = Vector8.unpack_from(bytes_)
        bytes_ = bytes_[Vector8.size():]
        phys.velocity = Vector8.unpack_from(bytes_)
        return phys
    
    unpack_from = unpack
    
    @classmethod
    def size(cls, bytes_=None):
        return 1 + Float8.size() + (2 * Vector8.size())
    
def mathutils_hash(obj): return hash(tuple(obj))

# Register custom types

register_handler(Vector, lambda attr: Vector8 if attr._kwargs.get("max_precision") else Vector4, is_condition=True)
register_handler(PhysicsData, PhysicsHandler)
register_handler(AnimationData, AnimationHandler)

# Register custom hash-like descriptions
register_description(Vector, mathutils_hash)
register_description(Euler, mathutils_hash)