from network import Enum

class PhysicsType(metaclass=Enum):
    values = "none", "static_body", "rigid_body"