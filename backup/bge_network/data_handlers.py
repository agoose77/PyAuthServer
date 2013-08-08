from network import Float8, Float4, UInt8, String, register_handler, register_description, WorldInfo
from .data_types import *

class Euler8:
    float_pack = Float8.pack
    float_unpack = Float8.unpack
    float_size = Float8.size()
    
    wrapper = Euler
    wrapper_length = 3
    
    @classmethod
    def pack(cls, euler):
        pack = cls.float_pack
        return b''.join(pack(c) for c in euler)
    
    @classmethod
    def unpack(cls, bytes_):
        packer_size = cls.float_size
        unpack = cls.float_unpack
        return cls.wrapper((unpack(bytes_[i * packer_size: (i + 1) * packer_size]) for i in range(cls.wrapper_length)))
    
    @classmethod
    def unpack_merge(cls, euler, bytes_):
        packer_size = cls.float_size
        unpack = cls.float_unpack
        euler[:] = (unpack(bytes_[i * packer_size: (i + 1) * packer_size]) for i in range(cls.wrapper_length))
        
    @classmethod
    def size(cls, bytes_=None):
        return cls.float_size * cls.wrapper_length
        
    unpack_from = unpack    

class Euler4(Euler8):   
    float_pack = Float4.pack
    float_unpack = Float4.unpack
    float_size = Float4.size() 

class Vector8(Euler8):
    wrapper = Vector
    
class Vector4(Euler4):
    wrapper = Vector

class Quaternion4(Euler4):
    wrapper = Quaternion
    wrapper_length = 4

class Quaternion8(Euler8):
    wrapper = Quaternion
    wrapper_length = 4

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
    float_unpack = Float8.unpack_from
    vector_unpack = Vector8.unpack_from
    quaternion_unpack = Quaternion8.unpack_from
    
    float_pack = Float8.pack
    vector_pack = Vector8.pack
    quaternion_pack =  Quaternion8.pack
    
    float_size = Float8.size()
    vector_size = Vector8.size()
    quaternion_size =  Quaternion8.size()
    
    @classmethod
    def pack(cls, phys):
        vector_pack = cls.vector_pack
        phys.timestamp = WorldInfo.elapsed
        data = UInt8.pack(phys.mode), cls.float_pack(phys.timestamp), vector_pack(phys.position), vector_pack(phys.velocity), vector_pack(phys.angular), cls.quaternion_pack(phys.orientation)
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
        phys.orientation = cls.quaternion_unpack(bytes_)
        return phys
    
    unpack_from = unpack
    
    @classmethod
    def size(cls, bytes_ = None):
        return 1 + cls.float_size + (3 * cls.vector_size) + cls.quaternion_size

class InputHandler:
    int_pack = UInt8.pack
    int_unpack = UInt8.unpack
    string_pack = String.pack
    string_unpack = String.unpack_from
    string_size = String.size
    
    @classmethod
    def pack(cls, inputs):
        input_class = inputs.__class__
        ordered_mappings = input_class._ordered_mappings
        status_dict = inputs._cache
        pack = cls.int_pack
        packed_members = b''.join(pack(status_dict[i].status) for i in ordered_mappings)
        return cls.string_pack(input_class.type_name) + packed_members
    
    @classmethod 
    def unpack(cls, bytes_):
        unpack = cls.int_unpack
        input_name = cls.string_unpack(bytes_)        
        input_class = InputManager.from_type_name(input_name)
        bytes_ = bytes_[cls.string_size(bytes_):]
        inputs = input_class()
        input_values = (unpack(bytes_[i:i+1]) for i in range(len(input_class._ordered_mappings)))
        inputs._events = dict((input_class.mappings[name], value) for (name, value) in zip(input_class._ordered_mappings, input_values))
        return inputs
    
    @classmethod
    def unpack_merge(cls, inputs, bytes_):
        inputs_new = cls.unpack(bytes_)
        inputs._events.update(inputs_new._events)
        
    @classmethod
    def size(cls, bytes_=None):
        input_class = InputManager.from_type_name(cls.string_unpack(bytes_))
        return cls.string_size(bytes_) + len(input_class._ordered_mappings)
    
    unpack_from = unpack
    
def mathutils_hash(obj): return hash(tuple(obj))

# Register custom types

register_handler(Vector, lambda attr: Vector8 if attr._kwargs.get("max_precision") else Vector4, is_condition=True)
register_handler(Euler, lambda attr: Euler8 if attr._kwargs.get("max_precision") else Euler4, is_condition=True)
register_handler(Quaternion, lambda attr: Quaternion8 if attr._kwargs.get("max_precision") else Quaternion4, is_condition=True)
register_handler(PhysicsData, PhysicsHandler)
register_handler(AnimationData, AnimationHandler)
register_handler(InputManager, InputHandler)

# Register custom hash-like descriptions
register_description(Vector, mathutils_hash)
register_description(Euler, mathutils_hash)