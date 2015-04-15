from game_system.enums import ButtonState, InputButtons
from game_system.coordinates import Vector
from game_system.inputs import InputState

from direct.showbase import DirectObject


__all__ = ['PandaInputManager', 'PandaMouseManager']


panda_to_input_button_key = {'a': 'AKEY', '\\': 'BACKSLASHKEY', 'backspace': 'BACKSPACEKEY',
    'b': 'BKEY', 'caps_lock': 'CAPSLOCKKEY', 'c': 'CKEY', ',': 'COMMAKEY', 'delete': 'DELKEY',
    'd': 'DKEY', 'arrow_down': 'DOWNARROWKEY', '8': 'EIGHTKEY', 'e': 'EKEY', 'end': 'ENDKEY',
    'enter': 'ENTERKEY', '=': 'EQUALKEY', 'escape': 'ESCKEY', 'f10': 'F10KEY', 'f11': 'F11KEY', 'f12': 'F12KEY',
    'f13': 'F13KEY', 'f14': 'F14KEY', 'f15': 'F15KEY', 'f16': 'F16KEY', 'f17': 'F17KEY', 'f18': 'F18KEY',
    'f19': 'F19KEY', 'f1': 'F1KEY', 'f2': 'F2KEY', 'f3': 'F3KEY', 'f4': 'F4KEY', 'f5': 'F5KEY', 'f6': 'F6KEY',
    'f7': 'F7KEY', 'f8': 'F8KEY', 'f9': 'F9KEY', '5': 'FIVEKEY', 'f': 'FKEY', '4': 'FOURKEY', 'g': 'GKEY',
    'h': 'HKEY', 'home': 'HOMEKEY', 'i': 'IKEY', 'insert': 'INSERTKEY', 'j': 'JKEY', 'k': 'KKEY',
    'lalt': 'LEFTALTKEY', 'arrow_left': 'LEFTARROWKEY', '[': 'LEFTBRACKETKEY', 'lcontrol': 'LEFTCTRLKEY',
    'mouse1': 'LEFTMOUSE', 'lshift': 'LEFTSHIFTKEY', 'l': 'LKEY', 'mouse2': 'MIDDLEMOUSE', '-': 'MINUSKEY',
    'm': 'MKEY', '9': 'NINEKEY', 'n': 'NKEY', 'o': 'OKEY', '1': 'ONEKEY', 'meta': 'OSKEY',
    'page_down': 'PAGEDOWNKEY', 'page_up': 'PAGEUPKEY', 'pause': 'PAUSEKEY', '.': 'PERIODKEY', 'p': 'PKEY',
    'q': 'QKEY', '\'': 'QUOTEKEY', 'ralt': 'RIGHTALTKEY', 'arrow_right': 'RIGHTARROWKEY',
    ']': 'RIGHTBRACKETKEY', 'rcontrol': 'RIGHTCTRLKEY', 'mouse3': 'RIGHTMOUSE', 'rshift': 'RIGHTSHIFTKEY',
    'r': 'RKEY', ';': 'SEMICOLONKEY', '7': 'SEVENKEY', '6': 'SIXKEY', 's': 'SKEY', '/': 'SLASHKEY',
    'space': 'SPACEKEY', 'tab': 'TABKEY', '3': 'THREEKEY', 't': 'TKEY', '2': 'TWOKEY', 'u': 'UKEY',
    'arrow_up': 'UPARROWKEY', 'v': 'VKEY', 'wheel_down': 'WHEELDOWNMOUSE', 'wheel_up': 'WHEELUPMOUSE',
    'w': 'WKEY', 'x': 'XKEY', 'y': 'YKEY', '0': 'ZEROKEY', 'z': 'ZKEY'}


panda_to_input_button = {k: getattr(InputButtons, v) for k, v in panda_to_input_button_key.items()}
input_button_values = set(InputButtons.values_to_keys)


class PandaInputManager(DirectObject.DirectObject):
    """Input manager for Panda3D"""

    def __init__(self):
        self.state = InputState()
        self.mouse_manager = PandaMouseManager()

        self._down_events = set()

    def update(self):
        # Get Panda state
        is_down = base.mouseWatcherNode.is_button_down

        active_events = {v for k, v in panda_to_input_button.items() if is_down(k)}
        entered_events = active_events - self._down_events
        released_events = input_button_values - active_events

        # Build converted state
        PRESSED = ButtonState.pressed
        HELD = ButtonState.held
        RELEASED = ButtonState.released

        converted_events = {e: HELD for e in active_events}
        converted_events.update({e: PRESSED for e in entered_events})
        converted_events.update({e: RELEASED for e in released_events})

        self.state.buttons = converted_events

        # Update ranges
        self.mouse_manager.update()

        delta_x, delta_y = self.mouse_manager.delta_position
        self.state.ranges['mouse_delta_x'] = delta_x
        self.state.ranges['mouse_delta_y'] = delta_y

        x, y = self.mouse_manager.position
        self.state.ranges['mouse_x'] = x
        self.state.ranges['mouse_y'] = y

        # Clear event sets
        self._down_events = active_events


class PandaMouseManager:

    def __init__(self):
        self.position = Vector((0.0, 0.0))
        self._last_position = Vector((0.0, 0.0))

    @property
    def delta_position(self):
        return self.position - self._last_position

    def update(self):
        """Process new mouse state"""
        mouse_node = base.mouseWatcherNode

        if mouse_node.hasMouse():
            x = mouse_node.getMouseX()
            y = mouse_node.getMouseY()

            position = Vector((x, y))
            self._last_position, self.position = self.position, position