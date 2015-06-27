from network.type_flag import TypeFlag
from network.handlers import get_handler, register_description, register_handler, IHandler

from functools import partial
from itertools import chain

from .coordinates import Vector, Euler, Quaternion, Matrix

__all__ = ["EulerHandler", "VectorHandler", "QuaternionHandler", "MatrixHandler"]


def unpack_handler(handler):
    return handler.pack, handler.unpack_from, handler.size()


class PrecisionSwitcher:
    precision = None

    def __new__(cls, flag, logger):
        # If the class being instantiated is a subclass
        if cls.precision is not None:
            new_cls = cls

        else:
            requires_high_precision = flag.data.get("max_precision")
            for new_cls in cls.__subclasses__():
                if requires_high_precision and new_cls.precision == "high":
                    break

                elif not requires_high_precision and new_cls.precision == "low":
                    break

        return object.__new__(new_cls)


class MathutilsHandler(PrecisionSwitcher, IHandler):

    wrapper = None
    wrapper_length = 3

    item_pack = None
    item_size = None
    item_unpack = None

    flag = None

    def __init__(self, flag, logger):
        self.packer = packer = get_handler(self.flag)
        self.item_pack = packer.pack
        self.item_unpack = packer.unpack_from
        self.item_size = packer.size()

    def pack(self, obj):
        pack = self.item_pack
        return b''.join(pack(c) for c in obj)

    def unpack_from(self, bytes_string, offset=0):
        item_size = self.item_size
        unpack = self.item_unpack
        wrapper_length = self.wrapper_length
        iterable = [unpack(bytes_string, offset + (i * item_size))[0]
                    for i in range(wrapper_length)]

        return self.wrapper(iterable), item_size * wrapper_length

    def unpack_merge(self, euler, bytes_string, offset=0):
        item_size = self.item_size
        unpack = self.item_unpack
        wrapper_length = self.wrapper_length

        euler[:] = [unpack(bytes_string, offset + (i * item_size))[0] for i in range(wrapper_length)]
        return item_size * wrapper_length

    def size(self, bytes_string=None):
        return self.item_size * self.wrapper_length


class EulerHandler(MathutilsHandler):

    wrapper = Euler


class Euler8Handler(EulerHandler):

    flag = TypeFlag(float, max_precision=True)
    precision = "high"


class Euler4Handler(EulerHandler):

    flag = TypeFlag(float, max_precision=False)
    precision = "low"


class VectorHandler(MathutilsHandler):

    wrapper = Vector


class Vector8Handler(VectorHandler):

    flag = TypeFlag(float, max_precision=True)
    precision = "high"


class Vector4Handler(VectorHandler):

    flag = TypeFlag(float, max_precision=False)
    precision = "low"


class QuaternionHandler(MathutilsHandler):

    wrapper = Quaternion
    wrapper_length = 4


class Quaternion8Handler(QuaternionHandler):

    flag = TypeFlag(float, max_precision=True)
    precision = "high"


class Quaternion4Handler(QuaternionHandler):

    flag = TypeFlag(float, max_precision=False)
    precision = "low"


class MatrixHandler(MathutilsHandler):

    wrapper = Matrix
    wrapper_length = 9


class Matrix8Handler(MatrixHandler):

    flag = TypeFlag(Vector, max_precision=True)
    precision = "high"


class Matrix4Handler(MatrixHandler):

    flag = TypeFlag(Vector, max_precision=False)
    precision = "low"


def matrix_description(obj):
    return hash(tuple(chain.from_iterable(obj)))


def vector_description(obj):
    return hash(tuple(obj))


# Register handlers
register_handler(Vector, VectorHandler)
register_handler(Euler, EulerHandler)
register_handler(Quaternion, QuaternionHandler)
register_handler(Matrix, MatrixHandler)

# Register custom hash-like descriptions
register_description(Vector, vector_description)
register_description(Euler, vector_description)
register_description(Quaternion, vector_description)
register_description(Matrix, matrix_description)
