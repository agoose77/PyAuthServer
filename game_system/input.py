# Remove playercontroller
# Add input component
# Set bindings on input component (copy from cls component)
# component.set_alias('w', 'forward')
# server-side map to input component


class InputComponent:

    def __init__(self):
        pass


class InputComponentInstance:

    def __init__(self):
        self.aliases = {}
        self.events = {}


class InputManagerBase:

    def __init__(self):
        self._components = set()

    def register_component(self, component):
        self._components.add(component)

    def deregister_component(self, component):
        self._components.remove(component)

    @property
    def current_events(self):
        raise NotImplementedError

    @property
    def mouse_position(self):
        raise NotImplementedError

    def update(self):
        events = self.current_events
        mouse_pos = self.mouse_position

        for component in self._components:
            component.events = {a: events[e] for e, a in component.aliases.items()}
            component.mouse_position = mouse_pos