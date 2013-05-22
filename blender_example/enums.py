from network import Enum

class Physics(metaclass=Enum):
    values = "none", "projectile", "rigidbody", "character"
    
class Animations(metaclass=Enum):
    values = "play", "loop"     