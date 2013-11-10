from bge import logic, types
from functools import wraps
from math import radians
from mathutils import Vector, Euler, Quaternion, Matrix
from network import (Float8, Float4, register_handler,
                     register_description, Struct, Attribute)

class RigidBodyState(Struct):

    position = Attribute(Vector())
    velocity = Attribute(Vector())
    angular = Attribute(Vector())
    rotation = Attribute(Euler())


class EngineObject:

    def __init__(self, name):
        self.owner = None

    def __new__(cls, obj_name, *args, **kwargs):
        scene = logic.getCurrentScene()
        # create a location matrix
        mat_loc = kwargs.get("position", Matrix.Translation((0, 0, 1)))
        # create an identitiy matrix
        mat_sca = kwargs.get("scale", Matrix.Identity(4))
        # create a rotation matrix
        mat_rot = kwargs.get("rotation", Matrix.Identity(4))
        # combine transformations
        mat_out = mat_loc * mat_rot * mat_sca
        obj = scene.addObject(obj_name, mat_out, 0, -1)
        return super().__new__(cls, obj)

    @property
    def all_children(self):
        yield from self.childrenRecursive
        if self.groupMembers:
            for child in self.groupMembers:
                yield from child.childrenRecursive


class GameObject(EngineObject, types.KX_GameObject):
    pass


class Socket(GameObject):
    pass


class CameraObject(EngineObject, types.KX_Camera):
    pass


class ArmatureObject(EngineObject, types.BL_ArmatureObject):
    pass


class NavmeshObject(EngineObject, types.KX_NavMeshObject):
    pass


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
        return cls.wrapper((unpack(bytes_[i * packer_size: (i + 1) * \
                          packer_size]) for i in range(cls.wrapper_length)))

    @classmethod
    def unpack_merge(cls, euler, bytes_):
        packer_size = cls.float_size
        unpack = cls.float_unpack
        euler[:] = (unpack(bytes_[i * packer_size: (i + 1) * packer_size])
                    for i in range(cls.wrapper_length))

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
register_handler(Vector, lambda attr: Vector8 if \
             attr.data.get("max_precision") else Vector4, is_condition=True)
register_handler(Euler, lambda attr: Euler8 if \
             attr.data.get("max_precision") else Euler4, is_condition=True)
register_handler(Quaternion, lambda attr: Quaternion8 if \
         attr.data.get("max_precision") else Quaternion4, is_condition=True)

# Register custom hash-like descriptions
register_description(Vector, mathutils_description)
register_description(Euler, mathutils_description)
