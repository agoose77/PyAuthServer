from network.enums import Enumeration


__all__ = ['PhysicsType', 'EvaluationState', 'CameraMode',
           'MovementState', 'AIState', 'Axis', 'CollisionGroups',
           'AnimationMode', 'AnimationBlend', 'CollisionState',
           'InputEvents', 'AudioDistanceModel']


class PhysicsType(metaclass=Enumeration):
    """Enumeration of Physics Types"""
    values = ("static", "dynamic", "rigid_body", "soft_body", "occluder",
              "sensor", "navigation_mesh", "character", "no_collision")


class EvaluationState(metaclass=Enumeration):
    values = "success", "failed", "running", "ready"


class CameraMode(metaclass=Enumeration):
    values = ("first_person", "third_person")


class MovementState(metaclass=Enumeration):
    values = ("run", "walk", "static")


class AIState(metaclass=Enumeration):
    values = ("idle", "alert", "engage")


class Axis(metaclass=Enumeration):
    values = ("x", "y", "z")


class CollisionGroups(metaclass=Enumeration):
    use_bits = True
    values = ("geometry", "pawn", "projectile")


class CollisionState(metaclass=Enumeration):
    values = ("started", "ended")


class AnimationMode(metaclass=Enumeration):
    values = ("play", "loop", "ping_pong", "stop")


class AnimationBlend(metaclass=Enumeration):
    values = ("interpolate", "add")


class EventType(metaclass=Enumeration):
    values = ("action_in", "action_out", "state")


class InputEvents(metaclass=Enumeration):

    values = ('ACCENTGRAVEKEY', 'AKEY', 'BACKSLASHKEY', 'BACKSPACEKEY',
              'BKEY', 'CAPSLOCKKEY', 'CKEY', 'COMMAKEY', 'DELKEY',
              'DKEY', 'DOWNARROWKEY', 'EIGHTKEY', 'EKEY', 'ENDKEY',
              'ENTERKEY', 'EQUALKEY', 'ESCKEY', 'F10KEY', 'F11KEY', 'F12KEY',
              'F13KEY', 'F14KEY', 'F15KEY', 'F16KEY', 'F17KEY', 'F18KEY', 'F19KEY',
              'F1KEY', 'F2KEY', 'F3KEY', 'F4KEY', 'F5KEY', 'F6KEY', 'F7KEY',
              'F8KEY', 'F9KEY', 'FIVEKEY', 'FKEY', 'FOURKEY', 'GKEY', 'HKEY',
              'HOMEKEY', 'IKEY', 'INSERTKEY', 'JKEY', 'KKEY', 'LEFTALTKEY',
              'LEFTARROWKEY', 'LEFTBRACKETKEY', 'LEFTCTRLKEY', 'LEFTMOUSE',
              'LEFTSHIFTKEY', 'LINEFEEDKEY', 'LKEY', 'MIDDLEMOUSE', 'MINUSKEY',
              'MKEY', 'MOUSEX', 'MOUSEY', 'NINEKEY', 'NKEY', 'OKEY', 'ONEKEY',
              'OSKEY', 'PAD0', 'PAD1', 'PAD2', 'PAD3', 'PAD4', 'PAD5', 'PAD6',
              'PAD7', 'PAD8', 'PAD9', 'PADASTERKEY', 'PADENTER', 'PADMINUS',
              'PADPERIOD', 'PADPLUSKEY', 'PADSLASHKEY', 'PAGEDOWNKEY',
              'PAGEUPKEY', 'PAUSEKEY', 'PERIODKEY', 'PKEY', 'QKEY', 'QUOTEKEY',
              'RETKEY', 'RIGHTALTKEY', 'RIGHTARROWKEY', 'RIGHTBRACKETKEY',
              'RIGHTCTRLKEY', 'RIGHTMOUSE', 'RIGHTSHIFTKEY', 'RKEY',
              'SEMICOLONKEY', 'SEVENKEY', 'SIXKEY', 'SKEY', 'SLASHKEY',
              'SPACEKEY', 'TABKEY', 'THREEKEY', 'TKEY', 'TWOKEY', 'UKEY',
              'UPARROWKEY', 'VKEY', 'WHEELDOWNMOUSE', 'WHEELUPMOUSE', 'WKEY',
              'XKEY', 'YKEY', 'ZEROKEY', 'ZKEY')


class AudioDistanceModel(metaclass=Enumeration):

    values = ("linear",)