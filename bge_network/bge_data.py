from bge import logic, types
from functools import wraps

from network import Float8, Float4, UInt8, String, register_handler, register_description, WorldInfo, Struct, Attribute
from mathutils import Vector, Euler, Quaternion, Matrix

class RigidBodyState(Struct):
    
    def __init__(self):
        super().__init__()
        
        self._modified = self.__description__()
        
    @property
    def modified(self):
        return self._modified == self.__description__()
    
    @modified.setter
    def modified(self, status):
        if not status:
            self._modified = self.__description__()
    
    position = Attribute(Vector())
    velocity = Attribute(Vector())
    angular = Attribute(Vector())
    rotation = Attribute(Euler())

class EngineObject:
    
    def __new__(cls, obj_name, *args, **kwargs):
        scene = logic.getCurrentScene()
        obj = scene.addObject(obj_name, scene.objects['Cube'], 0)
        return super().__new__(cls, obj)
    
class GameObject(EngineObject, types.KX_GameObject):
        
    def __init__(self, name):
        self.owner = None
    
    def attach_to(self, target):
        assert isinstance(target, types.KX_GameObject)
        self.setParent(target)
    
    def detatch(self):
        self.removeParent()
    
    def destroy(self):
        self.endObject()

class Socket(GameObject):
    
    def attatch(self, obj):
        obj.attach_to(self)
        obj.localOrientation.zero()

class Armature(EngineObject, types.BL_ArmatureObject):
    
    def __init__(self, name):
        self.owner = None
    
    def attach_to(self, target):
        assert isinstance(target, types.KX_GameObject)
        self.setParent(target)
    
    def detatch(self):
        self.removeParent()
    
    def destroy(self):
        self.endObject()
        
    @property
    def sockets(self):
        return {s.name: s for s in self.childrenRecursive() if "socket" in s}

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

def mathutils_description(obj):
    return hash(tuple(obj))

# Register packers
register_handler(Vector, lambda attr: Vector8 if attr._kwargs.get("max_precision") else Vector4, is_condition=True)
register_handler(Euler, lambda attr: Euler8 if attr._kwargs.get("max_precision") else Euler4, is_condition=True)
register_handler(Quaternion, lambda attr: Quaternion8 if attr._kwargs.get("max_precision") else Quaternion4, is_condition=True)

# Register custom hash-like descriptions
register_description(Vector, mathutils_description)
register_description(Euler, mathutils_description)