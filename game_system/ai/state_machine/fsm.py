from .state import State


class FiniteStateMachine:

    def __init__(self):
        self._states = set()
        self._state = None

    @property
    def state(self):
        return self._state

    @state.setter
    def state(self, state):
        if self._state is not None:
            self._state.on_exit()

        if state is not None:
            state.on_enter()

        self._state = state

    def add_state(self, state, set_default=True):
        self._states.add(state)
        state.manager = self

        # Set default state if none set
        if set_default and self._state is None:
            self._state = state
            state.on_enter()

    def remove_state(self, state):
        state.on_exit()
        state.manager = None

        if self._state is state:
            self._state = None

        self._states.remove(state)