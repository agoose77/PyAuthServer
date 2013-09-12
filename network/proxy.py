from .network import WorldInfo
from .errors import ReplicableAccessError
from .handler_interfaces import get_handler, register_handler
from .descriptors import StaticValue
from .actors import Replicable

from weakref import proxy as weak_proxy


class ReplicableProxy:
    """Lazy loading proxy to Replicable references
    Used to send references over the network"""
    __slots__ = ["reference", "instance_id", "__weakref__"]

    def __init__(self, instance_id):
        object.__setattr__(self, "instance_id", instance_id)

    @property
    def _obj(self):
        '''Returns the reference when valid, or None when invalid'''
        try:
            return object.__getattribute__(self, "reference")

        except AttributeError:
            instance_id = object.__getattribute__(self, "instance_id")

            # Get the instance by instance id
            try:
                replicable_instance = WorldInfo.get_replicable(instance_id)
            except LookupError:
                return

            # Don't return proxy to local authorities
            if replicable_instance._local_authority:
                return

            child = weak_proxy(replicable_instance)
            object.__setattr__(self, "reference", child)

            return child

    def __getattribute__(self, name):
        target = object.__getattribute__(self, "_obj")
        try:
            return getattr(target, name)
        except AttributeError:
            if target is None:
                raise ReplicableAccessError()
            raise

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

    def __bool__(self):
        return bool(object.__getattribute__(self, "_obj"))

    _special_names = [
        '__abs__', '__add__', '__and__', '__call__', '__cmp__',
        '__coerce__', '__contains__', '__delitem__', '__delslice__',
        '__div__', '__divmod__', '__eq__', '__float__', '__floordiv__',
        '__ge__', '__getitem__', '__getslice__', '__gt__', '__hash__',
        '__hex__', '__iadd__', '__iand__', '__idiv__', '__idivmod__',
        '__ifloordiv__', '__ilshift__', '__imod__',  '__imul__',
        '__int__', '__invert__', '__ior__', '__ipow__', '__irshift__',
        '__isub__', '__iter__', '__itruediv__', '__ixor__', '__le__',
        '__len__', '__long__', '__lshift__', '__lt__', '__mod__',
        '__mul__', '__ne__', '__neg__', '__oct__', '__or__', '__pos__',
        '__pow__', '__radd__', '__rand__', '__rdiv__', '__rdivmod__',
        '__reduce__', '__reduce_ex__', '__repr__', '__reversed__',
        '__rfloorfiv__', '__rlshift__', '__rmod__', '__rmul__',
        '__ror__', '__rpow__', '__rrshift__', '__rshift__', '__rsub__',
        '__rtruediv__', '__rxor__', '__setitem__', '__setslice__',
        '__sub__', '__truediv__', '__xor__', 'next',
    ]

    @classmethod
    def _create_class_proxy(cls, theclass):
        """creates a proxy for the given class"""

        def make_method(name):
            def method(self, *args, **kw):
                method = getattr(object.__getattribute__(self, "_obj"), name)
                return method(*args, **kw)
            return method

        namespace = {}
        for name in cls._special_names:
            if hasattr(theclass, name):
                namespace[name] = make_method(name)
        return type("{}({})".format(cls.__name__, theclass.__name__),
                                                    (cls,), namespace)

    def __new__(cls, obj, *args, **kwargs):
            """
            creates a proxy instance referencing `obj`.
            (obj, *args, **kwargs) are passed to this class' __init__,
            so deriving classes can define an __init__ method of their own.
            note: _class_proxy_cache is unique per deriving class
            (each deriving class must hold its own cache)
            """
            try:
                cache = cls.__dict__["_class_proxy_cache"]
            except KeyError:
                cls._class_proxy_cache = cache = {}

            try:
                theclass = cache[obj.__class__]
            except KeyError:
                theclass = cache[obj.__class__] = cls._create_class_proxy(
                                                              obj.__class__)
            ins = object.__new__(theclass)
            theclass.__init__(ins, obj, *args, **kwargs)
            return ins


class ReplicableProxyBaseHandler:
    """Handler for packing replicable proxy
    Packs replicable references and unpacks to proxy OR reference"""

    def __init__(self):
        self._maximum_replicables = 255
        self._packer = get_handler(StaticValue(int,
                                   max_value=self._maximum_replicables))

    @property
    def maximum_replicables(self):
        return self._maximum_replicables

    @maximum_replicables.setter
    def maximum_replicables(self, value):
        self._maximum_replicables = value
        self._packer = get_handler(StaticValue(int, max_value=value))

    def pack(self, replicable):
        # Send the instance ID
        return self.pack_id(replicable.instance_id)

    def pack_id(self, id_):
        return self._packer.pack(id_)

    def unpack_id(self, bytes_):
        return self._packer.unpack_from(bytes_)

    def unpack(self, bytes_):
        instance_id = self.unpack_id(bytes_)

        # Return only a replicable that was created by the network
        try:
            replicable = WorldInfo.get_replicable(instance_id)
            # Check that it was made locally and has a remote role
            # replicable.roles.remote != Roles.none
            assert replicable._local_authority
            return weak_proxy(replicable)

        # We can't be sure that this is the correct instance
        # Use proxy to delay checks
        # Also, in past revisions: hoping it will have now been replicated
        except (LookupError, AssertionError):
            return ReplicableProxy(instance_id)

    def size(self, bytes_=None):
        return self._packer.size(bytes_)

    unpack_from = unpack

ReplicableProxyHandler = ReplicableProxyBaseHandler()
register_handler(Replicable, ReplicableProxyHandler)
