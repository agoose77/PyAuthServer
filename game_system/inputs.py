from network.bitfield import BitField
from network.type_flag import TypeFlag
from network.handler_interfaces import get_handler, register_handler

from .enums import EventType
from .tagged_delegate import EnvironmentDefinitionByTag

from collections import OrderedDict
from contextlib import contextmanager

__all__ = ['MouseManager', 'InputManager', 'InputPacker']


class InputManager:

    def __init__(self):
        self.in_actions = {}
        self.out_actions = {}
        self.states = {}
        self.translator = None

        self.active_states = set()

    def add_listener(self, event, event_type, listener):
        event_dict = self.get_event_dict(event_type)
        event_dict.setdefault(event, []).append(listener)

    def get_event_dict(self, event_type):
        if event_type == EventType.action_in:
            event_dict = self.in_actions

        elif event_type == EventType.action_out:
            event_dict = self.out_actions

        elif event_type == EventType.state:
            event_dict = self.states

        else:
            raise TypeError("Invalid event type {} given".format(event_type))

        return event_dict

    def get_view_writer(self, *events):
        def write():
            active_events = self.active_states
            return [e in active_events for e in events]

        return write

    def get_view_reader(self, *events):
        def read(view):
            active_events = [e for e, v in zip(events, view) if v]
            self.update(active_events)

        return read

    def remove_listener(self, event, event_type, listener):
        event_dict = self.get_event_dict(event_type)

        try:
            listeners = event_dict[event]

        except KeyError:
            raise LookupError("No listeners for {} are registered".format(event))

        listeners.append(listener)

    def update(self, events):
        if callable(self.translator):
            events = self.translator(events)

        all_events = set(events)
        active_events = self.active_states

        for new_event in all_events.difference(active_events):
            if new_event in self.in_actions:
                listeners = self.in_actions[new_event]
                self.call_listeners(listeners)

        for old_event in active_events.difference(all_events):
            if old_event in self.out_actions:
                listeners = self.out_actions[old_event]
                self.call_listeners(listeners)

        self.active_states = all_events

        for event in all_events:
            if event in self.states:
                listeners = self.states[event]
                self.call_listeners(listeners)

    @staticmethod
    def call_listeners(listeners):
        for listener in listeners:
            listener()


class InputManager(EnvironmentDefinitionByTag):
    """Manager for user input"""

    subclasses = {}

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


class MouseManager(EnvironmentDefinitionByTag):

    subclasses = {}


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
