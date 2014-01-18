from network import Enum


class PhysicsType(metaclass=Enum):
    values = ("static", "dynamic", "rigid_body", "soft_body", "occluder",
              "sensor", "navigation_mesh", "character", "no_collision")


class ShotType(metaclass=Enum):
    values = ("instant", "projectile")


class CameraMode(metaclass=Enum):
    values = ("first_person", "third_person")


class MovementState(metaclass=Enum):
    values = ("run", "walk", "static")


class AIState(metaclass=Enum):
    values = ("idle", "alert", "engage")


class Axis(metaclass=Enum):
    values = ("x", "y", "z")


class CollisionGroups(metaclass=Enum):
    use_bits = True
    values = ("geometry", "pawns")


class AnimationMode(metaclass=Enum):
    values = ("play", "loop", "ping_pong", "stop")


class AnimationBlend(metaclass=Enum):
    values = ("interpolate", "add")
