from collections import namedtuple


RayTestResult = namedtuple("RayTestResult", "position normal entity distance")
CollisionResult = namedtuple("CollisionResult", "entity state contacts")
CollisionContact = namedtuple("CollisionContact", "position normal impulse")
