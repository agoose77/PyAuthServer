from network import Enum

class PhysicsType(metaclass=Enum):
    values = "none", "rigid_body", "static_body"