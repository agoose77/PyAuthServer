from .coordinates import Vector
from .enums import EventType

__all__ = ['InputManager', 'MouseManager']


class _InputManager:

    def __init__(self):
        self._in_actions = {}
        self._out_actions = {}
        self._states = {}

        self.active_states = set()

    def add_listener(self, event, event_type, listener):
        event_dict = self._get_event_dict(event_type)
        event_dict.setdefault(event, []).append(listener)

    def _get_event_dict(self, event_type):
        if event_type == EventType.action_in:
            event_dict = self._in_actions

        elif event_type == EventType.action_out:
            event_dict = self._out_actions

        elif event_type == EventType.state:
            event_dict = self._states

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
        event_dict = self._get_event_dict(event_type)

        try:
            listeners = event_dict[event]

        except KeyError:
            raise LookupError("No listeners for {} are registered".format(event))

        listeners.append(listener)

    def update(self, events):
        all_events = set(events)
        active_events = self.active_states

        for new_event in all_events.difference(active_events):
            if new_event in self._in_actions:
                listeners = self._in_actions[new_event]
                self._call_listeners(listeners)

        for old_event in active_events.difference(all_events):
            if old_event in self._out_actions:
                listeners = self._out_actions[old_event]
                self._call_listeners(listeners)

        self.active_states = all_events

        for event in all_events:
            if event in self._states:
                listeners = self._states[event]
                self._call_listeners(listeners)

    @staticmethod
    def _call_listeners(listeners):
        for listener in listeners:
            listener()


class _MouseManager:

    def __init__(self):
        self.position = Vector((0.0, 0.0))
        self._last_position = Vector()
        self.visible = False

    @property
    def delta_position(self):
        return self.position - self._last_position

    def update(self, position, visible):
        self._last_position = self.position
        self._position = position
        self.visible = visible


MouseManager = _MouseManager()
InputManager = _InputManager()