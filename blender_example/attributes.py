from network import WorldInfo, Replicable, Float8, Float4, UInt8, String, register_handler, register_description
from weakref import proxy as weak_proxy
from mathutils import Vector, Euler
from itertools import chain

class LazyReplicableProxy:
    """Lazy loading proxy to Replicable references
    Used to send references over the network"""
    __slots__ = ["obj", "target", "__weakref__"]
    
    def __init__(self, target):
        object.__setattr__(self, "target", target)
        
    @property
    def _obj(self):
        '''Returns the reference when valid, or None when invalid'''
        try:
            return object.__getattribute__(self, "obj")
        except AttributeError:
            network_id = object.__getattribute__(self, "target")
            try:
                replicable_instance = WorldInfo.get_actor(network_id)
            except KeyError:
                return
            else:
                child = weak_proxy(replicable_instance)
                object.__setattr__(self, "obj", child)
                return child
        
    def __getattribute__(self, name):
        return getattr(object.__getattribute__(self, "_obj"), name)
    
    def __delattr__(self, name):
        delattr(object.__getattribute__(self, "_obj"), name)
        
    def __setattr__(self, name, value):
        setattr(object.__getattribute__(self, "_obj"), name, value)
        
    def __nonzero__(self):
        return bool(object.__getattribute__(self, "_obj"))
    
    def __str__(self):
        return str(object.__getattribute__(self, "_obj"))
    
    def __repr__(self):
        return repr(object.__getattribute__(self, "_obj"))
    
    
    _special_names = [
        '__abs__', '__add__', '__and__', '__call__', '__cmp__', '__coerce__', 
        '__contains__', '__delitem__', '__delslice__', '__div__', '__divmod__', 
        '__eq__', '__float__', '__floordiv__', '__ge__', '__getitem__', 
        '__getslice__', '__gt__', '__hash__', '__hex__', '__iadd__', '__iand__',
        '__idiv__', '__idivmod__', '__ifloordiv__', '__ilshift__', '__imod__', 
        '__imul__', '__int__', '__invert__', '__ior__', '__ipow__', '__irshift__', 
        '__isub__', '__iter__', '__itruediv__', '__ixor__', '__le__', '__len__', 
        '__long__', '__lshift__', '__lt__', '__mod__', '__mul__', '__ne__', 
        '__neg__', '__oct__', '__or__', '__pos__', '__pow__', '__radd__', 
        '__rand__', '__rdiv__', '__rdivmod__', '__reduce__', '__reduce_ex__', 
        '__repr__', '__reversed__', '__rfloorfiv__', '__rlshift__', '__rmod__', 
        '__rmul__', '__ror__', '__rpow__', '__rrshift__', '__rshift__', '__rsub__', 
        '__rtruediv__', '__rxor__', '__setitem__', '__setslice__', '__sub__', 
        '__truediv__', '__xor__', 'next',
    ]
    
    @classmethod
    def _create_class_proxy(cls, theclass):
        """creates a proxy for the given class"""
        
        def make_method(name):
            def method(self, *args, **kw):
                return getattr(object.__getattribute__(self, "_obj"), name)(*args, **kw)
            return method
        
        namespace = {}
        for name in cls._special_names:
            if hasattr(theclass, name):
                namespace[name] = make_method(name)
        return type("%s(%s)" % (cls.__name__, theclass.__name__), (cls,), namespace)
    
    def __new__(cls, obj, *args, **kwargs):
        """
        creates an proxy instance referencing `obj`. (obj, *args, **kwargs) are
        passed to this class' __init__, so deriving classes can define an 
        __init__ method of their own.
        note: _class_proxy_cache is unique per deriving class (each deriving
        class must hold its own cache)
        """
        try:
            cache = cls.__dict__["_class_proxy_cache"]
        except KeyError:
            cls._class_proxy_cache = cache = {}#keyeddefaultdict(cls._create_class_proxy)
        
        try:
            theclass = cache[obj.__class__]
        except KeyError:
            theclass = cache[obj.__class__] = cls._create_class_proxy(obj.__class__)
        ins = object.__new__(theclass)
        theclass.__init__(ins, obj, *args, **kwargs)
        return ins
    
class ReplicableProxyHandler:
    """Handler for packing replicable proxy
    Packs replicable references and unpacks to proxy OR reference"""
    
    @classmethod
    def pack(cls, replicable):
        return UInt8.pack(replicable.network_id)
    
    @classmethod
    def unpack(cls, bytes_):
        network_id = UInt8.unpack_from(bytes_)
        try:
            replicable = WorldInfo.get_actor(network_id)
        except KeyError:
            return LazyReplicableProxy(network_id)
        else:
            return weak_proxy(replicable)
    
    unpack_from = unpack    
    size = UInt8.size
    
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
register_handler(Replicable, ReplicableProxyHandler)

# Register custom hash-like descriptions
register_description(Vector, mathutils_hash)
register_description(Euler, mathutils_hash)