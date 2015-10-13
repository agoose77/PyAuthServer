from .finite_state_machine import FiniteStateMachine, State


class InputHandlingState(State):

    def handle_input(self, input_state):
        pass


class InputHandlingStateMachine(FiniteStateMachine):

    def handle_input(self, input_state):
        current_state = self.state

        if current_state is None:
            return

        new_state = current_state.handle_input(input_state)
        if new_state is None:
            return

        self.state = new_state