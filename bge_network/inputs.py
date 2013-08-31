from bge import events, logic
from network import FactoryDict, Bitfield, StaticValue, get_handler, register_handler
from functools import partial

class EventInterface:
    def __init__(self, name, status):
        self.name = name
        self.get_status = status
    
    @property
    def status(self):
        return self.get_status(self.name)
    
    @property
    def active(self):
        return self.status == logic.KX_INPUT_ACTIVE or self.status == logic.KX_INPUT_JUST_ACTIVATED
        
class InputManager:
    def __init__(self, keybindings, status_lookup=None):
        self.keybindings = keybindings
        self.status_lookup = status_lookup if status_lookup is not None else self.default_lookup
        
        self._event_interfaces = FactoryDict(self.new_event_interface)
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
        return (self._event_interfaces[k].active for k in sorted(self.keybindings))
    
    def choose_device(self, name):
        binding_code = self.keybindings[name]
        return logic.keyboard if binding_code in logic.keyboard.events else logic.mouse
    
    def default_lookup(self, name):
        binding_code = self.keybindings[name]
        device = self._devices_for_keybindings[name]
        return device.events[binding_code]
    
    def new_event_interface(self, name):
        return EventInterface(name, self.status_lookup)
    
    def __getattr__(self, name):
        return self._event_interfaces[name]
    
    def __str__(self):
        data = []
        for key in self.keybindings:
            data.append("{}:{}".format(key, getattr(self, key).active))
        return "Input Manager:" + ', '.join(data)
    
class InputPacker:
    handler = get_handler(StaticValue(Bitfield))
    
    def __init__(self, static_value):
        self.fields = static_value.data['fields']
    
    def pack(self, input_):
        values = Bitfield.from_iterable([getattr(input_, name).active for name in self.fields])
        return self.handler.pack(values)
    
    def to_active(self, data, name):
        return logic.KX_INPUT_ACTIVE if data[name] else logic.KX_INPUT_NONE
    
    def unpack(self, bytes_):
        values = Bitfield(len(self.fields))
        self.handler.unpack_merge(values, bytes_)
        data = dict(zip(self.fields, values))
        return InputManager(data, status_lookup=partial(self.to_active, data))
    
    unpack_from = unpack
    size = handler.size
    
# Register handler for input manager
register_handler(InputManager, InputPacker, True)
    