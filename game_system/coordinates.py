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

if 0:
    try:
        from mathutils import *

    except ImportError:
        try:
            from ._mathutils import *
        except ImportError as err:
            raise ImportError("Unable to import mathutils library") from err
