from collections import deque

from .state import State


class PushdownAutomaton:

    def __init__(self):
        self._stack = deque()

    @property
    def state(self):
        if not self._stack:
            return None

        return self._stack[-1]

    def push(self, state):
        if self._stack:
            self._stack[-1].on_exit()

        self._stack.append(state)
        state.on_enter()

    def pop(self):
        state = self._stack.pop()
        state.on_exit()

        if self._stack:
            self._stack[-1].on_enter()