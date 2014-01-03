from bge import events, logic
from network import FactoryDict, Bitfield, TypeFlag, get_handler, register_handler
from functools import partial
import bge


class EventInterface:
    def __init__(self, name, status):
        self.name = name
        self.get_status = status

    @property
    def status(self):
        return self.get_status(self.name)

    @property
    def active(self):
        return self.status == logic.KX_INPUT_ACTIVE or \
            self.status == logic.KX_INPUT_JUST_ACTIVATED


class InputManager:
    def __init__(self, keybindings, status_lookup=None):
        self.keybindings = keybindings

        if status_lookup is None:
            self.status_lookup = self.default_lookup
        else:
            self.status_lookup = status_lookup

        self._devices_for_keybindings = FactoryDict(self.choose_device)

    def using_interface(self, lookup_func):
        self._lookup = self.status_lookup
        self.status_lookup = lookup_func
        return self

    def restore_interface(self, *args, **kwargs):
        self.status_lookup = self._lookup

    def __enter__(self):
        pass

    def __exit__(self, *args):
        self.restore_interface()

    def to_tuple(self):
        return tuple(self.status_lookup(k) for k in sorted(self.keybindings))

    def choose_device(self, name):
        binding_code = self.keybindings[name]
        keyboard = logic.keyboard
        return keyboard if binding_code in keyboard.events else logic.mouse

    def default_lookup(self, name):
        binding_code = self.keybindings[name]
        device = self._devices_for_keybindings[name]
        return device.events[binding_code] in (logic.KX_INPUT_ACTIVE,
                                               logic.KX_INPUT_JUST_ACTIVATED)

    def __getattr__(self, name):
        if name in self.keybindings:
            return self.status_lookup(name)
        raise AttributeError("Input manager does not have {} binding"
                            .format(name))

    def __str__(self):
        lookup = self.status_lookup
        data = [("{}: {}".format(key, lookup(key))) for key in self.keybindings]
        return "[Input Manager] " + ', '.join(data)


class InputPacker:
    handler = get_handler(TypeFlag(Bitfield))

    def __init__(self, static_value):
        self._fields = static_value.data['input_fields']

    def pack(self, input_):
        fields = self._fields
        values = Bitfield.from_iterable([getattr(input_, name)
                                         for name in fields])
        return self.handler.pack(values)

    def unpack(self, bytes_):
        fields = self._fields

        values = Bitfield(len(fields))
        self.handler.unpack_merge(values, bytes_)

        data = dict(zip(fields, values))

        return InputManager(data, status_lookup=data.__getitem__)

    unpack_from = unpack
    size = handler.size

# Register handler for input manager
register_handler(InputManager, InputPacker, True)
