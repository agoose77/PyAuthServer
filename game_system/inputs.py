from network.bitfield import BitField
from network.descriptors import TypeFlag
from network.handler_interfaces import get_handler, register_handler

from collections import OrderedDict
from contextlib import contextmanager

__all__ = ['IInputStatusLookup', 'BGEInputStatusLookup', 'MouseManager',
           'InputManager', 'InputPacker']


class IInputStatusLookup:
    """Base class for a Status Lookup interface"""

    def __call__(self, event):
        raise NotImplementedError()


class InputManager:
    """Manager for user input"""

    def __init__(self, ordered_keybindings, status_lookup):
        self.status_lookup = status_lookup
        self.ordered_keybindings = ordered_keybindings
        self.keybinding_indices = None

    @contextmanager
    def using_interface(self, lookup_func):
        previous_lookup_func = self.status_lookup
        self.status_lookup = lookup_func
        yield
        self.status_lookup = previous_lookup_func

    def to_tuple(self):
        """Create an ordered tuple mapping of input names to statuses"""
        return tuple(self.status_lookup(binding) for binding in self.ordered_keybindings.values())

    def to_dict(self):
        """Create a dictionary mapping of input names to statuses"""
        return {name: self.status_lookup(binding) for name, binding in self.ordered_keybindings.items()}

    def copy(self):
        """Create a read-only copy of the current input state"""
        field_names, field_codes = zip(*self.ordered_keybindings.items())

        # Save doing this again
        if self.keybinding_indices is None:
            self.keybinding_indices = OrderedDict((name, i) for i, name in enumerate(field_names))

        get_status = self.status_lookup
        status_from_index = [get_status(code) for code in field_codes].__getitem__

        return InputManager(self.keybinding_indices, status_from_index)

    def __getattr__(self, name):
        try:
            event_code = self.ordered_keybindings[name]

        except KeyError as err:
            raise AttributeError("Input manager does not have {} binding".format(name)) from err

        return self.status_lookup(event_code)

    def __str__(self):
        prefix = "[Input Manager]\n"
        state = self.to_dict()
        contents = ["  {}={}".format(name, state[name]) for name in self.ordered_keybindings]
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
        self._keybinding_indices = OrderedDict((name, index) for index, name in enumerate(self._fields))
        self._bitfield_packer = get_handler(TypeFlag(BitField, fields=len(self._fields)))

    def pack(self, input_):
        values = BitField.from_iterable([getattr(input_, name) for name in self._fields])
        return self._bitfield_packer.pack(values)

    def unpack_from(self, bytes_string, offset=0):
        values, value_size = self._bitfield_packer.unpack_from(bytes_string, offset)
        inputs = InputManager(self._keybinding_indices, status_lookup=values.__getitem__)
        return inputs, value_size

    def size(self, bytes_string):
        return self._bitfield_packer.size(bytes_string)


# Register handler for input manager
register_handler(InputManager, InputPacker, True)
