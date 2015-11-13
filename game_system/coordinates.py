from network.type_serialisers import register_serialiser, register_describer, get_serialiser_for, \
    TypeSerialiserAbstract, TypeDescriberAbstract

try:
    from mathutils import *

except ImportError:
    try:
        from .mathutils import *
    except ImportError as err:
        raise ImportError("Unable to import mathutils library") from err


class MathutilsHandler(TypeSerialiserAbstract):

    wrapper = None
    wrapper_length = 3

    item_pack = None
    item_size = None
    item_unpack = None

    flag = None

    def __init__(self, type_info, logger):
        self.packer = packer = get_serialiser_for(float, max_precision=type_info.data.get("max_precision"))
        self.multiple_pack = packer.pack_multiple
        self.multiple_unpack = packer.unpack_multiple
        self.item_size = packer.size()

    def pack(self, obj):
        return self.multiple_pack(obj, self.wrapper_length)

    def unpack_from(self, bytes_string, offset=0):
        iterable, bytes_read = self.multiple_unpack(bytes_string, self.wrapper_length, offset=offset)

        return self.wrapper(iterable), bytes_read

    def unpack_merge(self, euler, bytes_string, offset=0):
        euler[:], bytes_read = self.multiple_unpack(bytes_string, self.wrapper_length, offset=offset)
        return bytes_read

    def size(self, bytes_string=None):
        return self.item_size * self.wrapper_length


class EulerHandler(MathutilsHandler):

    wrapper = Euler


class VectorHandler(MathutilsHandler):

    wrapper = Vector


class QuaternionHandler(MathutilsHandler):

    wrapper = Quaternion
    wrapper_length = 4


class MatrixHandler(MathutilsHandler):

    wrapper = Matrix
    wrapper_length = 9


def matrix_description(obj):
    return hash(tuple(chain.from_iterable(obj)))


def vector_description(obj):
    return hash(tuple(obj))


# Register handlers
register_serialiser(Vector, VectorHandler)
register_serialiser(Euler, EulerHandler)
register_serialiser(Quaternion, QuaternionHandler)
register_serialiser(Matrix, MatrixHandler)

def generic_describer(func):
    class GenericDescriber(TypeDescriberAbstract):

        def __init__(self, type_info):
            pass

        def __call__(self, obj):
            if obj is None:
                obj = ()

            return func(obj)

    return GenericDescriber


register_describer(Euler, generic_describer(vector_description))
register_describer(Vector, generic_describer(vector_description))
register_describer(Quaternion, generic_describer(vector_description))
register_describer(Matrix, generic_describer(matrix_description))