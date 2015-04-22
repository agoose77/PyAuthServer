from network.struct import Struct
from network.descriptors import Attribute

from .coordinates import Vector, Euler


class RigidBodyState(Struct):
    """Struct for Rigid Body Physics information"""
    position = Attribute(data_type=Vector)
    velocity = Attribute(data_type=Vector)
    angular = Attribute(data_type=Vector)
    rotation = Attribute(data_type=Euler)

    collision_group = Attribute(data_type=int)
    collision_mask = Attribute(data_type=int)

    def lerp(self, other, factor):
        self.position += (other.position - self.position) * factor
        self.velocity += (other.velocity - self.velocity) * factor
        self.angular += (other.angular - self.angular) * factor

        target_rotation = other.rotation.to_quaternion()
        rotation = self.rotation.to_quaternion()

        rotation.slerp(target_rotation, factor)
        self.rotation = rotation.to_euler()


class AnimationState(Struct):
    """Struct for Animation information"""

    layer = Attribute(0)
    start = Attribute(0)
    end = Attribute(0)
    blend = Attribute(1.0)
    name = Attribute("")
    speed = Attribute(1.0)
    mode = Attribute(0)
    timestamp = Attribute(0.0)
