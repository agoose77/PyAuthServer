from collections import deque


class PushdownAutomaton:

    def __init__(self, logger=None):
        self._stack = deque()
        self._logger = logger

    @property
    def state(self):
        if not self._stack:
            return None

        return self._stack[-1]

    @state.setter
    def state(self, state):
        from_state = self.pop()

        if self._logger:
            self._logger.info("Transitioning from {} to {}".format(from_state, state))

        self.push(state)

    def push(self, state):
        if self._stack:
            self._stack[-1].on_exit()

        if self._logger:
            self._logger.info("Pushing {}".format(state))

        self._stack.append(state)
        state.on_enter()

    def pop(self):
        state = self._stack.pop()
        state.on_exit()

        if self._logger:
            self._logger.info("Popping {}".format(state))

        if self._stack:
            self._stack[-1].on_enter()

        return state
