from network.bitfield import BitField
from network.descriptors import TypeFlag
from network.handler_interfaces import get_handler, register_handler
from network.structures import FactoryDict

from bge import events, logic, render
from collections import OrderedDict
from contextlib import contextmanager
from mathutils import Vector

from .utilities import clamp

__all__ = ['IInputStatusLookup', 'BGEInputStatusLookup', 'MouseManager',
           'InputManager', 'InputPacker']


class IInputStatusLookup:
    """Base class for a Status Lookup interface"""

    def __call__(self, event):
        raise NotImplementedError()


class BGEInputStatusLookup(IInputStatusLookup):
    """BGE interface for Input Status lookups"""

    def __init__(self):
        self._event_list_containing = FactoryDict(self._get_containing_events)

    def __call__(self, event):
        events = self._event_list_containing[event]
        return events[event] in (logic.KX_INPUT_ACTIVE,
                                 logic.KX_INPUT_JUST_ACTIVATED)

    def _get_containing_events(self, event):
        keyboard = logic.keyboard
        return (keyboard.events if event in keyboard.events
                else logic.mouse.events)


class MouseManager:

    def __init__(self, locked=True, interpolation=1):
        self.window_size = Vector((render.getWindowWidth(),
                                   render.getWindowHeight()))
        self.center = Vector(((self.window_size.x//2)/self.window_size.x,
                              (self.window_size.y//2)/self.window_size.y))
        self.locked = locked
        self.interpolation = interpolation

        self._delta_position = Vector((0.0, 0.0))
        self._last_position = self.position

    @property
    def delta_position(self):
        return self._delta_position

    @property
    def position(self):
        return Vector(logic.mouse.position)

    @position.setter
    def position(self, position):
        screen_x = int(position[0] * self.window_size.x)
        screen_y = int(position[1] * self.window_size.y)
        render.setMousePosition(screen_x, screen_y)

    @property
    def visible(self):
        return logic.mouse.visible

    @visible.setter
    def visible(self, state):
        logic.mouse.visible = state

    def update(self):
        self.position.x = clamp(0, 1, self.position.x)
        self.position.y = clamp(0, 1, self.position.y)
        delta_position = self._last_position - self.position

        self._delta_position = self._delta_position.lerp(delta_position,
                                                         self.interpolation)

        if self.locked:
            # As mouse position isn't actually (0.5, 0.5)
            self.position = self.center.copy()
            last_position = self.center.copy()

        else:
            last_position = self.position.copy()

        self._last_position = last_position


class InputManager:
    """Manager for user input"""

    def __init__(self, keybindings, status_lookup):
        assert isinstance(keybindings, OrderedDict)
        self.status_lookup = status_lookup
        self._keybindings_to_events = keybindings

    @contextmanager
    def using_interface(self, lookup_func):
        previous_lookup_func = self.status_lookup
        self.status_lookup = lookup_func
        yield
        self.status_lookup = previous_lookup_func

    def to_tuple(self):
        return tuple(self.status_lookup(binding) for binding in
                     self._keybindings_to_events.values())

    def to_dict(self):
        return OrderedDict((name, self.status_lookup(binding))
                   for name, binding in self._keybindings_to_events.items())

    def copy(self):
        field_names = self._keybindings_to_events.keys()
        field_codes = self._keybindings_to_events.values()

        get_status = self.status_lookup

        indexed_fields = OrderedDict((name, i) for i, name in enumerate(field_names))
        state_tuple = tuple(get_status(code) for code in field_codes)

        return InputManager(indexed_fields, state_tuple.__getitem__)

    def __getattr__(self, name):
        try:
            event_code = self._keybindings_to_events[name]

        except KeyError as err:
            raise AttributeError("Input manager does not have {} binding"
                            .format(name)) from err

        return self.status_lookup(event_code)

    def __str__(self):
        prefix = "[Input Manager] \n"
        contents = ["  {}={}".format(name, state) for name, state in
                    self.to_dict().items()]
        return prefix + "\n".join(contents)


#==============================================================================
# TODO: profile code
# Latency predominantly on Server
# Either in unpacking methods, or in attribute lookups
# Perhaps in how Inputs are unpacked
#==============================================================================


class InputPacker:

    def __init__(self, static_value):
        self._fields = static_value.data['fields']
        self._field_count = len(self._fields)

        self._keybinding_index_map = OrderedDict((name, index) for index, name
                                                 in enumerate(self._fields))

        self._packer = get_handler(TypeFlag(BitField,
                                            fields=len(self._fields)
                                            )
                                   )

    def pack(self, input_):
        values = BitField.from_iterable([getattr(input_, name) for name in
                                         self._fields])
        return self._packer.pack(values)

    def unpack(self, bytes_):
        # Unpack input states to
        values = self._packer.unpack_from(bytes_)

        return InputManager(self._keybinding_index_map,
                            status_lookup=values.__getitem__)

    def size(self, bytes_):
        return self._packer.size(bytes_)

    unpack_from = unpack

# Register handler for input manager
register_handler(InputManager, InputPacker, True)
