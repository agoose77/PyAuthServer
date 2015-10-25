class Timer:

    def __init__(self, delay, repeat=False):
        self._time = 0.0

        self.repeat = repeat
        self.delay = delay

        self.on_elapsed = None

    @property
    def done(self):
        return self._time > self.delay

    def update(self, dt):
        self._time += dt

        if self._time > self.delay:
            if callable(self.on_elapsed):
                self.on_elapsed()

            if self.repeat:
                self._time = 0.0

            else:
                self.on_elapsed = None
                return True

        return False