from collections import deque, namedtuple


State = namedtuple("State", "tick position orientation")


class InterpolationWindow:

    def __init__(self):
        self._window = deque(maxlen=6)
        self._current_tick = None
        self._can_read = False
        self._full_length = 3

    def add_frame(self, tick, position, orientation):
        if not self._window:
            self._current_tick = tick

        self._window.append(State(tick, position, orientation))

        if len(self._window) == self._full_length:
            self._can_read = True

    def next_sample(self):
        if not self._can_read:
            raise ValueError()

        current_tick = self._current_tick
        self._current_tick += 1

        state = None
        next_state = None

        while self._window:
            state = self._window[0]

            try:
                next_state = self._window[1]

            except IndexError:
                # Need another state!
                self._can_read = False
                print("Ran out of state")

                raise ValueError()

            if next_state.tick < current_tick:
                self._window.popleft()

            else:
                break

        factor = (current_tick - state.tick) / (next_state.tick - state.tick)

        position = state.position.lerp(next_state.position, factor)
        orientation = state.orientation.slerp(next_state.orientation, factor)

        return position, orientation