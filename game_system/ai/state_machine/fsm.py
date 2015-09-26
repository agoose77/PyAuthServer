from collections import defaultdict, namedtuple


Transition = namedtuple("Transition", ("condition", "from_state", "to_state"))


class FiniteStateMachine:

    def __init__(self, logger=None):
        self._state = None
        self._states = set()
        self._transitions = defaultdict(list)

        self._logger = logger

    @property
    def state(self):
        return self._state

    @state.setter
    def state(self, state):
        current_state = self._state
        if state is current_state:
            return

        if current_state is not None:
            if self._logger:
                self._logger.info("Exiting {}".format(current_state))

            current_state.on_exit()

        self._state = state

        if state is not None:
            if self._logger:
                self._logger.info("Entering {}".format(state))

            state.on_enter()

    def add_transition(self, transition):
        if self._logger:
            self._logger.info("Adding transition {}".format(transition))

        self._transitions[transition.from_state].append(transition)

    def create_and_add_transition(self, condition, from_state, to_state):
        transition = Transition(condition, from_state, to_state)
        self.add_transition(transition)
        return transition

    def create_and_add_transitions_from_table(self, table):
        transitions = []
        for transition_data in table:
            transition = self.create_and_add_transition(*transition_data)
            transitions.append(transition)

        return transitions

    def find_transitions_involving(self, state):
        involved_transitions = []

        for from_state, transitions in self._transitions.items():
            if from_state is state:
                involved_transitions.extend(transitions)

            else:
                for transition in transitions:
                    if transition.to_state is state:
                        involved_transitions.append(transition)

        return involved_transitions

    def process_transitions(self):
        current_state = self.state

        for transition in self._transitions[current_state]:
            if transition.condition():
                self.state = transition.to_state

                if self._logger:
                    self._logger.info("Transitioning from {} to {}"
                                      .format(current_state, transition.to_state))
                break

    def remove_transition(self, transition):
        if self._logger:
            self._logger.info("Removing transition {}".format(transition))

        self._transitions[transition.from_state].remove(transition)

    def add_state(self, state, set_default=True):
        self._states.add(state)
        state.manager = self

        # Set default state if none set
        if set_default and self._state is None:
            self._state = state
            state.on_enter()

            if self._logger:
                self._logger.info("Entering initial state: {}".format(state))

    def remove_state(self, state):
        if self._state is state:
            self._state = None

        self._states.remove(state)

        # Remove any dependent transitions
        for transition in self.find_transitions_involving(state):
            self.remove_transition(transition)

        if self._logger:
            self._logger.info("Exiting removed state {}".format(state))

        state.on_exit()
        state.manager = None
