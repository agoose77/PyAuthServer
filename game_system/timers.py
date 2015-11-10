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


class TimerManager:

    def __init__(self):
        self._timers = []

    def add_timer(self, delay, repeat=False):
        """Create timer object with a given delay

        :param delay: delay until timer is finished
        :param repeat: prevents timer from expiring
        """
        timer = Timer(delay, repeat)
        self._timers.append(timer)

        return timer

    def remove_timer(self, timer):
        """Remove timer from timer list.

        :param timer: Timer object
        """
        self._timers.remove(timer)

    def update(self, dt):
        """Update Timer objects"""
        finished_timers = set()

        for timer in self._timers:
            is_finished = timer.update(dt)

            if is_finished:
                finished_timers.add(timer)

        for timer in finished_timers:
            self.remove_timer(timer)
