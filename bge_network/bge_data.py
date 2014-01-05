from bge import logic, types
from mathutils import Matrix, Quaternion


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
        mat_rot = kwargs.get("rotation", Quaternion()).to_matrix().to_4x4()
        # combine transformations
        mat_out = mat_loc * mat_rot * mat_sca
        try:
            obj = scene.addObject(obj_name, mat_out, 0, -1)
        except ValueError:
            raise ValueError("Could not find object with name {}".format(obj_name))
        return super().__new__(cls, obj)

    @property
    def all_children(self):
        yield from self.childrenRecursive
        if self.groupMembers:
            for child in self.groupMembers:
                yield from child.childrenRecursive


class GameObject(EngineObject, types.KX_GameObject):
    pass


class CameraObject(EngineObject, types.KX_Camera):
    pass


class LampObject(EngineObject, types.KX_LightObject):
    pass


class ArmatureObject(EngineObject, types.BL_ArmatureObject):
    pass


class NavmeshObject(EngineObject, types.KX_NavMeshObject):
    pass

