class FiniteState:

    def __init__(self, func, identifier):
        self._func = func

        self.identifier = identifier
        self.branches = {}

    def add_branch(self, condition, transition, state):
        self.branches[condition] = state, transition

    def update_branches(self):
        for condition, state in self.branches.items():
            if condition(self):
                return state
        return self, None

    def run(self, *args, **kwargs):
        self._func(self, *args, **kwargs)


class FiniteStateMachine:

    def __init__(self):
        self.states = {}
        self.transitions = {}
        self.conditions = {}
        self._state = None

    def add_state(self, identifier, func):
        self.states[identifier] = FiniteState(func, identifier)

    def add_branch(self, from_identifier, to_identifier, condition,
                   transition=None):
        self.states[from_identifier].add_branch(condition, transition,
                                                self.states[to_identifier])

    def add_condition(self, to_identifier, condition):
        self.conditions[condition] = to_identifier

    def add_transition(self, to_identifier, transition):
        self.transitions[to_identifier] = transition

    def get_state(self, identifier):
        return self.states[identifier]

    @property
    def current_state(self):
        state_changed = False
        transition = None
        to_state = self._state

        if not self._state is None:
            to_state, transition = self._state.update_branches()
            state_changed = to_state is not self._state

        if not state_changed:
            for condition, to_state_identifier in self.conditions.items():
                if condition(self):
                    transition = self.transitions[to_state_identifier]
                    to_state = self.states[to_state_identifier]

        if callable(transition):
            transition(self._state, to_state)

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
