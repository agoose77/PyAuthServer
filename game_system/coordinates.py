from network.type_serialisers import register_serialiser, register_describer, get_serialiser_for, TypeSerialiserAbstract


class Vector:

    def __init__(self, obj):
        self.x, self.y, self.z = obj

    def __add__(self, other):
        x,y,z=other
        return Vector((self.x+x, self.y+y, self.z+z))

    def __iter__(self):
        return iter((self.x, self.y, self.z))


class Euler:
    def __init__(self, obj):
        self.x, self.y, self.z = obj

    def __add__(self, other):
        x,y,z=other
        return Vector((self.x+x, self.y+y, self.z+z))

    def __iter__(self):
        return iter((self.x, self.y, self.z))


class VectPacker(TypeSerialiserAbstract):
    handler = get_serialiser_for(float)

    cls = Vector

    def __init__(self, type_info, logger):
        super().__init__(type_info, logger)

        self.packer = self.handler.pack_multiple
        self.unpacker = self.handler.unpack_multiple

    def pack(self, value):
        return self.packer(value, 3)

    def unpack_from(self, bytes_string, offset=0):
        data, bytes_read = self.unpacker(bytes_string, 3, offset=offset)
        return self.cls(data), bytes_read

    def size(self, bytes_string):
        return self.handler.size() * 3


class EulerPacker(VectPacker):
    cls = Euler


class describe_type:
    def __init__(self, tp):
        pass

    def __call__(self, obj):
        if obj is None:
            obj = ()

        return hash(tuple(obj))


register_serialiser(Euler, EulerPacker)
register_serialiser(Vector, VectPacker)

register_describer(Euler, describe_type)
register_describer(Vector, describe_type)

if 0:
    try:
        from mathutils import *

    except ImportError:
        try:
            from ._mathutils import *
        except ImportError as err:
            raise ImportError("Unable to import mathutils library") from err
