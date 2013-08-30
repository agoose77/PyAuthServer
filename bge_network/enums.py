from network import Enum

class PhysicsType(metaclass=Enum):
    values = "static", "dynamic", "rigid_body", "soft_body", "occluder", "sensor", "navigation_mesh", "character", "no_collision"