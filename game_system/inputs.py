from .coordinates import Vector
from .enums import ListenerType

__all__ = ['InputManager', 'MouseManager']


class _InputManager:
    """Interface to input handlers"""

    def __init__(self):
        self._in_actions = {}
        self._out_actions = {}
        self._states = {}

        self.active_states = set()

    def add_listener(self, event, listener_type, listener):
        """Add event listener for given event type
        :param event: event name
        :param listener_type: type of listener
        :param listener: callback function
        """
        event_dict = self._get_event_dict(listener_type)
        event_dict.setdefault(event, []).append(listener)

    def _get_event_dict(self, listener_type):
        """Return the appropriate event dictionary for listener

        :param listener_type: type of listener
        """
        if listener_type == ListenerType.action_in:
            event_dict = self._in_actions

        elif listener_type == ListenerType.action_out:
            event_dict = self._out_actions

        elif listener_type == ListenerType.state:
            event_dict = self._states

        else:
            raise TypeError("Invalid event type {} given".format(listener_type))

        return event_dict

    def get_bound_view(self, *events):
        """Return bound view function for given events

        :param events: ordered events (as arguments) to bind to view
        """
        def write():
            active_events = self.active_states
            return [e in active_events for e in events]

        return write

    def get_bound_writer(self, *events):
        """Return bound writer function for given events

        :param events: ordered events (as arguments) to write
        """
        def read(view):
            active_events = [e for e, v in zip(events, view) if v]
            self.update(active_events)

        return read

    def remove_listener(self, event, listener_type, listener):
        """Remove event listener for given event type
        :param event: event name
        :param listener_type: type of listener
        :param listener: callback function
        """
        event_dict = self._get_event_dict(listener_type)

        try:
            listeners = event_dict[event]

        except KeyError:
            raise LookupError("No listeners for {} are registered".format(event))

        listeners.remove(listener)

    def update(self, events):
        """Process new events and update listeners

        :param events: new events
        """
        all_events = set(events)
        active_events = self.active_states

        call_listeners = self._call_listeners
        for new_event in all_events.difference(active_events):
            if new_event in self._in_actions:
                listeners = self._in_actions[new_event]
                call_listeners(listeners)

        for old_event in active_events.difference(all_events):
            if old_event in self._out_actions:
                listeners = self._out_actions[old_event]
                call_listeners(listeners)

        self.active_states = all_events

        for event in all_events:
            if event in self._states:
                listeners = self._states[event]
                call_listeners(listeners)

    @staticmethod
    def _call_listeners(listeners):
        for listener in listeners:
            listener()


class _MouseManager:
    """Interface to mouse information"""

    def __init__(self):
        self.position = Vector((0.0, 0.0))
        self._last_position = Vector()
        self.visible = False

    @property
    def delta_position(self):
        return self.position - self._last_position

    def update(self, position, visible):
        """Process new mouse state

        :param position: new mouse position
        :param visible: new mouse visibility state
        """
        self._last_position = self.position
        self._position = position
        self.visible = visible


MouseManager = _MouseManager()
InputManager = _InputManager()