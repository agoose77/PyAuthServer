"""Serialiser data for Mathutils types"""

from network.descriptors import TypeFlag
from network.handler_interfaces import get_handler, register_description, register_handler

from functools import partial
from itertools import chain
from mathutils import Vector, Euler, Quaternion, Matrix

__all__ = ["Euler4", "Euler8", "Vector4", "Vector8", "Quaternion4",
           "Quaternion8", "Matrix4", "Matrix8"]


class Euler8:

    packer = get_handler(TypeFlag(float, max_precision=True))

    item_pack = packer.pack
    item_unpack = packer.unpack_from
    item_size = packer.size()

    wrapper = Euler
    wrapper_length = 3

    @classmethod
    def pack(cls, euler):
        pack = cls.item_pack
        return b''.join(pack(c) for c in euler)

    @classmethod
    def unpack_from(cls, bytes_string, offset=0):
        item_size = cls.item_size
        unpack = cls.item_unpack
        wrapper_length = cls.wrapper_length
        iterable = [unpack(bytes_string, offset + (i * item_size))[0] for i in range(wrapper_length)]

        return cls.wrapper(iterable), item_size * wrapper_length

    @classmethod
    def unpack_merge(cls, euler, bytes_string, offset=0):
        item_size = cls.item_size
        unpack = cls.item_unpack
        wrapper_length = cls.wrapper_length

        euler[:] = [unpack(bytes_string, offset + (i * item_size))[0] for i in range(wrapper_length)]
        return item_size * wrapper_length

    @classmethod
    def size(cls, bytes_string=None):
        return cls.item_size * cls.wrapper_length


class Euler4(Euler8):

    packer = get_handler(TypeFlag(float, max_precision=False))

    item_pack = packer.pack
    item_unpack = packer.unpack_from
    item_size = packer.size()


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


class Matrix4(Euler4):
    item_pack = Vector4.pack
    item_unpack = Vector4.unpack_from
    item_size = Vector4.size()
    wrapper_length = 3
    wrapper = Matrix


class Matrix8(Matrix4):
    item_pack = Vector8.pack
    item_unpack = Vector8.unpack_from
    item_size = Vector8.size()


def matrix_description(obj):
    return hash(tuple(chain.from_iterable(obj)))


def vector_description(obj):
    return hash(tuple(obj))


def precision_switch(low, high, type_flag):
    return high if type_flag.data.get("max_precision") else low


# Register packers
register_handler(Vector, partial(precision_switch, Vector4, Vector8), is_callable=True)
register_handler(Euler, partial(precision_switch, Euler4, Euler8), is_callable=True)
register_handler(Quaternion, partial(precision_switch, Quaternion4, Quaternion8), is_callable=True)
register_handler(Matrix, partial(precision_switch, Matrix4, Matrix8), is_callable=True)

# Register custom hash-like descriptions
register_description(Vector, vector_description)
register_description(Euler, vector_description)
register_description(Quaternion, vector_description)
register_description(Matrix, matrix_description)
