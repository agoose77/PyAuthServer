from mathutils import Vector, Euler, Quaternion, Matrix
from itertools import chain
from network import (Float8, Float4, register_handler,
                     register_description, Struct, Attribute)


class Euler8:
    item_pack = Float8.pack
    item_unpack = Float8.unpack
    item_size = Float8.size()

    wrapper = Euler
    wrapper_length = 3

    @classmethod
    def pack(cls, euler):
        pack = cls.item_pack
        return b''.join(pack(c) for c in euler)

    @classmethod
    def unpack(cls, bytes_):
        packer_size = cls.item_size
        unpack = cls.item_unpack
        return cls.wrapper((unpack(bytes_[i * packer_size: (i + 1) * \
                          packer_size]) for i in range(cls.wrapper_length)))

    @classmethod
    def unpack_merge(cls, euler, bytes_):
        packer_size = cls.item_size
        unpack = cls.item_unpack
        euler[:] = (unpack(bytes_[i * packer_size: (i + 1) * packer_size])
                    for i in range(cls.wrapper_length))

    @classmethod
    def size(cls, bytes_=None):
        return cls.item_size * cls.wrapper_length

    unpack_from = unpack


class Euler4(Euler8):
    item_pack = Float4.pack
    item_unpack = Float4.unpack
    item_size = Float4.size()


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
    item_unpack = Vector4.unpack
    item_size = Vector4.size()
    wrapper_length = 3
    wrapper = Matrix


class Matrix8(Matrix4):
    item_pack = Vector8.pack
    item_unpack = Vector8.unpack
    item_size = Vector8.size()


def matrix_description(obj):
    return hash(tuple(chain.from_iterable(obj)))


def mathutils_description(obj):
    return hash(tuple(obj))

# Register packers
register_handler(Vector, lambda attr: Vector8 if \
             attr.data.get("max_precision") else Vector4, is_condition=True)
register_handler(Euler, lambda attr: Euler8 if \
             attr.data.get("max_precision") else Euler4, is_condition=True)
register_handler(Quaternion, lambda attr: Quaternion8 if \
         attr.data.get("max_precision") else Quaternion4, is_condition=True)
register_handler(Matrix, lambda attr: Matrix8 if \
         attr.data.get("max_precision") else Matrix4, is_condition=True)

# Register custom hash-like descriptions
register_description(Vector, mathutils_description)
register_description(Euler, mathutils_description)
register_description(Quaternion, mathutils_description)
register_description(Matrix, matrix_description)
