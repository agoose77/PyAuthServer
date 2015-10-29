from network.type_serialisers import register_serialiser, register_describer, get_serialiser_for, \
    TypeSerialiserAbstract, TypeDescriberAbstract

try:
    from mathutils import *

except ImportError:
    try:
        from .mathutils import *
    except ImportError as err:
        raise ImportError("Unable to import mathutils library") from err


class VectorPacker(TypeSerialiserAbstract):
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


class EulerPacker(VectorPacker):
    cls = Euler


class Describe3Vector:

    def __init__(self, type_info):
        pass

    def __call__(self, obj):
        if obj is None:
            obj = ()

        return hash(tuple(obj))


register_serialiser(Euler, EulerPacker)
register_serialiser(Vector, VectorPacker)

register_describer(Euler, Describe3Vector)
register_describer(Vector, Describe3Vector)