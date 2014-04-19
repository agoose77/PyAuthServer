from bge import events, logic
from network import FactoryDict, BitField, TypeFlag, get_handler, register_handler
from contextlib import contextmanager


class IInputStatusLookup:

    def __call__(self, event):
        raise NotImplementedError()


class BGEInputStatusLookup(IInputStatusLookup):

    def __init__(self):
        self._event_list_containing = FactoryDict(self.get_containing_events)

    def __call__(self, event):
        events = self._event_list_containing[event]
        return events[event] in (logic.KX_INPUT_ACTIVE,
                                 logic.KX_INPUT_JUST_ACTIVATED)

    def get_containing_events(self, event):
        keyboard = logic.keyboard
        return (keyboard.events if event in keyboard.events
                else logic.mouse.events)


class InputManager:

    def __init__(self, keybindings, status_lookup):
        self.status_lookup = status_lookup
        self._keybindings_to_events = keybindings

    @contextmanager
    def using_interface(self, lookup_func):
        previous_lookup_func = self.status_lookup
        self.status_lookup = lookup_func
        yield
        self.status_lookup = previous_lookup_func

    def to_tuple(self):
        get_binding = self._keybindings_to_events.__getitem__
        return tuple(self.status_lookup(get_binding(name))
                     for name in sorted(self._keybindings_to_events))

    def __getattr__(self, name):
        try:
            event_code = self._keybindings_to_events[name]

        except KeyError as err:
            raise AttributeError("Input manager does not have {} binding"
                            .format(name)) from err

        return self.status_lookup(event_code)

    def __str__(self):
        print("[Input Manager]")
        for binding_name in self._keybindings_to_events.values():
            print("{}".format(binding_name))


class InputPacker:
    handler = get_handler(TypeFlag(BitField))

    def __init__(self, static_value):
        self._fields = static_value.data['input_fields']
        self._keybinding_index_map = {name: index for index, name
                                      in enumerate(self._fields)}

    def pack(self, input_):
        fields = self._fields
        values = BitField.from_iterable([getattr(input_, name)
                                         for name in fields])
        return self.handler.pack(values)

    def unpack(self, bytes_):
        fields = self._fields

        values = BitField(len(fields))
        self.handler.unpack_merge(values, bytes_)

        return InputManager(self._keybinding_index_map,
                            status_lookup=values.__getitem__)

    unpack_from = unpack
    size = handler.size

# Register handler for input manager
register_handler(InputManager, InputPacker, True)
