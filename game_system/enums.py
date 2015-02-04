from network.enums import Enumeration


__all__ = ['PhysicsType', 'EvaluationState', 'CameraMode', 'MovementState', 'AIState', 'Axis', 'CollisionGroups',
           'AnimationMode', 'AnimationBlend', 'CollisionState', 'InputButtons', 'AudioDistanceModel', 'ButtonState']


class PhysicsType(Enumeration):
    """Enumeration of Physics Types"""
    values = ("static", "dynamic", "rigid_body", "soft_body", "occluder",
              "sensor", "navigation_mesh", "character", "no_collision")


class EvaluationState(Enumeration):
    values = "success", "failure", "running", "ready"


class CameraMode(Enumeration):
    values = ("first_person", "third_person")


class MovementState(Enumeration):
    values = ("run", "walk", "static")


class AIState(Enumeration):
    values = ("idle", "alert", "engage")


class Axis(Enumeration):
    values = ("x", "y", "z")


class CollisionGroups(Enumeration):
    use_bits = True
    values = ("geometry", "pawn", "projectile")


class CollisionState(Enumeration):
    values = ("started", "ended")


class AnimationMode(Enumeration):
    values = ("play", "loop", "ping_pong", "stop")


class AnimationBlend(Enumeration):
    values = ("interpolate", "add")


class ListenerType(Enumeration):
    values = ("action_in", "action_out", "state")


class InputButtons(Enumeration):
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


class ButtonState(Enumeration):
    values = ('pressed', 'released', 'held')


class AudioDistanceModel(Enumeration):
    values = ("linear",)