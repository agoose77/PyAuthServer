from ..signals import LogicUpdateSignal


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
        if not callable(self._func):
            return

        self._func(self, *args, **kwargs)


class FiniteStateMachine:

    def __init__(self, initial_state=None):
        self.states = {}
        self.transitions = {}
        self.conditions = {}
        self.global_transitions = []

        self._state = None
        self._initial_identifier = initial_state
        self._reset_state = True

    def add_state(self, identifier, func, set_default=True):
        self.states[identifier] = FiniteState(func, identifier)

        if not self._initial_identifier and set_default:
            self._initial_identifier = identifier

    def add_branch(self, from_identifier, to_identifier, condition,
                   transition=None):
        self.states[from_identifier].add_branch(condition, transition,
                                                self.states[to_identifier])

    def add_condition(self, to_identifier, condition):
        self.conditions[condition] = to_identifier

    def add_transition(self, transition, to_identifier=None):
        if to_identifier is None:
            self.global_transitions.append(transition)
        else:
            self.transitions[to_identifier] = transition

    def reset(self, run=False):
        self._reset_state = True

        if run:
            self.update_state()

    def update_global_transitions(self, from_state, to_state):
        if self.global_transitions:
            for transition in self.global_transitions:
                transition(self, from_state, to_state)

    def update_state(self, last=None):
        # Check for reset
        if self._reset_state and self._initial_identifier:
            transition = self.transitions.get(self._initial_identifier)
            new_state = self.states[self._initial_identifier]

            if callable(transition):
                transition(self._state, new_state)
            self.update_global_transitions(self._state, new_state)

            self._reset_state = False
            self._state = new_state

            return self.update_state()

        # Check state conditions
        new_state, transition = self._state.update_branches()

        # Only run transition if change occurs
        if new_state is not self._state:
            if callable(transition):
                transition(self._state, new_state)
            self.update_global_transitions(self._state, new_state)
            self._state = new_state

        # Check global conditions
        for condition, to_state_identifier in self.conditions.items():

            if last != condition and condition(self):
                transition = self.transitions.get(to_state_identifier)
                new_state = self.states[to_state_identifier]

                if callable(transition):
                    transition(self._state, new_state)
                self.update_global_transitions(self._state, new_state)

                self._state = new_state

                return self.update_state(last=condition)

        return self._state

    @property
    def current_state(self):
        return self.update_state()

    @current_state.setter
    def current_state(self, state):
        try:
            state = self.states[state]
        except KeyError:
            assert isinstance(state, FiniteState), \
                "Unsupported state type, must be a valid \
                identifier or FiniteState subclass"
        self._state = state
        self._reset_state = False


class FSM(FiniteStateMachine):

    @LogicUpdateSignal.on_global
    def update(self, delta_time):
        self.update_state()(delta_time)
