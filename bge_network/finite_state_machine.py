class FiniteState:

    def __init__(self, func, identifier):
        self._func = func

        self.identifier = identifier
        self.branches = {}

    def add_branch(self, condition, state):
        self.branches[condition] = state

    def update_branches(self):
        for condition, state in self.branches.items():
            if condition(self):
                return state
        return self

    def run(self, *args, **kwargs):
        self._func(self, *args, **kwargs)


class FiniteStateMachine:

    def __init__(self):
        self.states = {}
        self.transitions = {}
        self._state = None

    def add_state(self, identifier, func):
        self.states[identifier] = FiniteState(func, identifier)

    def add_branch(self, from_identifier, to_identifier, condition):
        self.states[from_identifier].add_branch(condition,
                                                self.states[to_identifier])

    def add_transition(self, to_identifier, condition):
        self.transitions[condition] = to_identifier

    def get_state(self, identifier):
        return self.states[identifier]

    @property
    def current_state(self):
        state_changed = False
        if not self._state is None:
            to_state = self._state.update_branches()
            state_changed = to_state is not self._state

        if not state_changed:
            for condition, state in self.transitions.items():
                if condition(self):
                    to_state = state
                    break

        self._state = to_state
        return to_state

    @current_state.setter
    def current_state(self, state):
        try:
            state = self.states[state]
        except KeyError:
            assert isinstance(state, FiniteState), \
                "Unsupported state type, must be a valid \
                identifier or FiniteState subclass"
        self._state = state
