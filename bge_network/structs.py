from network import Struct, Attribute
from mathutils import Vector, Euler


class RigidBodyState(Struct):
    '''Struct for Rigid Body Physics information'''
    position = Attribute(Vector())
    velocity = Attribute(Vector())
    angular = Attribute(Vector())
    rotation = Attribute(Euler())

    collision_group = Attribute(type_of=int)
    collision_mask = Attribute(type_of=int)

    def lerp(self, other, factor):
        self.position += (other.position - self.position) * factor
        self.velocity += (other.velocity - self.velocity) * factor
        #print(self._container.data)
        #print(other.angular)
        res =  (other.angular - self.angular) * factor
        self.angular += res

        target_rotation = other.rotation.to_quaternion()
        rotation = self.rotation.to_quaternion()
        rotation.slerp(target_rotation, factor)
        self.rotation = rotation.to_euler()


class AnimationState(Struct):
    '''Struct for Animation information'''

    layer = Attribute(0)
    start = Attribute(0)
    end = Attribute(0)
    blend = Attribute(1.0)
    name = Attribute("")
    speed = Attribute(1.0)
    mode = Attribute(0)
    timestamp = Attribute(0.0)
