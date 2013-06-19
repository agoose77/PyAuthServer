from network import Float8, Float4, UInt8, String, register_handler, register_description
from .data_types import *

class Euler8:
    float_pack = Float8.pack
    float_unpack = Float8.unpack
    float_size = Float8.size()
    
    wrapper = Euler
    
    @classmethod
    def pack(cls, euler):
        pack = cls.float_pack
        return b''.join(pack(c) for c in euler)
    
    @classmethod
    def unpack(cls, bytes_):
        packer_size = cls.float_size
        unpack = cls.float_unpack
        return cls.wrapper((unpack(bytes_[i * packer_size: (i + 1) * packer_size]) for i in range(3)))
    
    @classmethod
    def unpack_merge(cls, euler, bytes_):
        packer_size = cls.float_size
        unpack = cls.float_unpack
        euler[:] = (unpack(bytes_[i * packer_size: (i + 1) * packer_size]) for i in range(3))
        
    @classmethod
    def size(cls, bytes_=None):
        return cls.float_size * 3
        
    unpack_from = unpack    

class Euler4(Euler8):   
    float_pack = Float4.pack
    float_unpack = Float4.unpack
    float_size = Float4.size() 

class Vector8(Euler8):
    wrapper = Vector
    
class Vector4(Euler4):
    wrapper = Vector

Vector4 = type("Vector4", (Vector8,), {})
Euler4 = type("Euler4", (Euler8,), {})

class AnimationHandler:
    @classmethod
    def pack(cls, anim):
        print("PACK")
        data = UInt8.pack(anim.mode), UInt8.pack(anim.start_frame), UInt8.pack(anim.end_frame), String.pack(anim.name), Float8.pack(anim.timestamp) 
        return b''.join(data)
    
    @classmethod
    def unpack(cls, bytes_):
        print(bytes_)
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
    float_unpack = Float8.unpack_from
    vector_unpack = Vector8.unpack_from
    euler_unpack = Euler8.unpack_from
    
    float_pack = Float8.pack
    vector_pack = Vector8.pack
    euler_pack = Euler8.pack
    
    float_size = Float8.size()
    vector_size = Vector8.size()
    euler_size = Euler8.size()
    
    @classmethod
    def pack(cls, phys):
        vector_pack = cls.vector_pack
        data = UInt8.pack(phys.mode), cls.float_pack(phys.timestamp), vector_pack(phys.position), vector_pack(phys.velocity), vector_pack(phys.angular), cls.euler_pack(phys.orientation)
        return b''.join(data)
        
    @classmethod
    def unpack(cls, bytes_):
        vector_unpack = cls.vector_unpack
        vector_size = cls.vector_size
        
        phys = PhysicsData(bytes_[0])
        bytes_ = bytes_[1:]
        phys.timestamp = cls.float_unpack(bytes_)
        bytes_ = bytes_[cls.float_size:]
        phys.position = vector_unpack(bytes_)
        bytes_ = bytes_[vector_size:]
        phys.velocity = vector_unpack(bytes_)
        bytes_ = bytes_[vector_size:]
        phys.angular = vector_unpack(bytes_)
        bytes_ = bytes_[vector_size:]
        phys.orientation = cls.euler_unpack(bytes_)
        return phys
    
    unpack_from = unpack
    
    @classmethod
    def size(cls, bytes_ = None):
        return 1 + cls.float_size + (3 * cls.vector_size) + cls.euler_size

class InputHandler:
    int_pack = UInt8.pack
    int_unpack = UInt8.unpack_from
    string_pack = String.pack
    string_unpack = String.unpack_from
    string_size = String.size
    
    @classmethod
    def pack(cls, inputs):
        input_class = inputs.__class__
        pack = cls.int_pack
        ordered_mappings = input_class._ordered_mappings
        status_dict = input_class._cache
        return cls.string_pack(input_class.type_name) + b''.join(pack(status_dict[i].status for i in ordered_mappings))
    
    @classmethod 
    def unpack(cls, bytes_):
        unpack = cls.unpack        
        input_class = InputManager.from_type_name(cls.string_unpack(bytes_))
        bytes_ = bytes_[cls.string_size(bytes_):]
        
        inputs = input_class()
        input_values = (unpack(bytes_) for i in range(len(bytes_)))
        inputs._events = dict((name, value) for name, value in zip(input_class._ordered_mappings, input_values))
        return inputs
    
    @classmethod
    def unpack_merge(cls, inputs, bytes_):
        inputs_new = cls.unpack(bytes_)
        inputs._events.update(inputs_new._events)
    
def mathutils_hash(obj): return hash(tuple(obj))

# Register custom types

register_handler(Vector, lambda attr: Vector8 if attr._kwargs.get("max_precision") else Vector4, is_condition=True)
register_handler(Euler, lambda attr: Euler8 if attr._kwargs.get("max_precision") else Euler4, is_condition=True)
register_handler(PhysicsData, PhysicsHandler)
register_handler(AnimationData, AnimationHandler)

# Register custom hash-like descriptions
register_description(Vector, mathutils_hash)
register_description(Euler, mathutils_hash)