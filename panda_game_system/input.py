from game_system.input import InputManagerBase
from panda3d.core import WindowProperties

from game_system.enums import ButtonStates, InputButtons
from game_system.coordinates import Vector


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
input_button_values = {v for k, v in InputButtons}


class InputManager(InputManagerBase):

    def __init__(self, world):
        super().__init__(world)

        self._down_events = set()

    def tick(self):
        # Select appropriate mouse mode
        if self.constrain_center_mouse:
            mouse_mode = WindowProperties.M_relative

        elif self.confine_mouse:
            mouse_mode = WindowProperties.M_confined

        else:
            mouse_mode = WindowProperties.M_absolute

        # Set mouse mode
        props = WindowProperties()
        props.set_mouse_mode(mouse_mode)
        props.set_cursor_hidden(not self.mouse_visible)
        base.win.requestProperties(props)

        # Get mouse position
        mouse_node = base.mouseWatcherNode
        if not mouse_node.hasMouse():
            return

        x = mouse_node.getMouseX()
        y = mouse_node.getMouseY()

        mouse_position = x, y

        last_mouse_position = self.mouse_position
        if last_mouse_position:
            last_x, last_y = last_mouse_position
            mouse_delta = (x - last_x, y - last_y)

        else:
            mouse_delta = (0.0, 0.0)

        # Set mouse position and delta
        self.mouse_position = mouse_position
        self.mouse_delta = mouse_delta

        # Get event states
        is_down = mouse_node.is_button_down
        active_events = {v for k, v in panda_to_input_button.items() if is_down(k)}
        entered_events = active_events - self._down_events
        released_events = input_button_values - active_events

        # Build converted state
        PRESSED = ButtonStates.pressed
        HELD = ButtonStates.held
        RELEASED = ButtonStates.released

        converted_events = {e: HELD for e in active_events}
        converted_events.update({e: PRESSED for e in entered_events})
        converted_events.update({e: RELEASED for e in released_events})

        self._down_events = active_events
        self.buttons_state = converted_events

        self._world.messenger.send("input_updated", input_manager=self)
