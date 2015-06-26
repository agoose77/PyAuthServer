from network.struct import Struct
from network.descriptors import Attribute

from .coordinates import Vector, Euler


class RigidBodyState(Struct):
    """Struct for Rigid Body Physics information"""
    position = Attribute(data_type=Vector)
    velocity = Attribute(data_type=Vector)
    angular = Attribute(data_type=Vector)
    orientation = Attribute(data_type=Euler)

    def lerp(self, other, factor):
        self.position += (other.position - self.position) * factor
        self.velocity += (other.velocity - self.velocity) * factor
        self.angular += (other.angular - self.angular) * factor

        target_rotation = other.rotation.to_quaternion()
        orientation = self.orientation.to_quaternion()

        orientation.slerp(target_rotation, factor)
        self.orientation = orientation.to_euler()


class RigidBodyInfo(Struct):
    """Struct for Rigid Body Physics information"""
    mass = Attribute(data_type=float)
    collision_group = Attribute(data_type=int)
    collision_mask = Attribute(data_type=int)


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
