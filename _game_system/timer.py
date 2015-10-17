from operator import (add as add_func, sub as sub_func,
                      lt as less_func, gt as more_func)

from network.signals import SignalListener
from .signals import TimerUpdateSignal


class ManualTimer:
    """Manual timer class with callbacks"""

    def __init__(self, end=0.0, start=0.0, count_down=False, repeat=False, active=True, disposable=False):

        # Initial values
        self.end = end
        self.start = self.value = start

        self.update_operator = sub_func if count_down else add_func
        self.comparison_operator = less_func if count_down else more_func

        # Callbacks
        self.on_target = None
        self.on_update = None
        self.on_stop = None
        self.on_reset = None

        # Behaviours
        self.repeat = repeat
        self.active = active
        self.disposable = disposable

    def delete(self):
        del self.on_target
        del self.on_update
        del self.on_stop
        del self.on_reset

        self.active = False

    @property
    def progress(self):
        total = self.end - self.start
        current = self.value - self.start
        return (1 / total) * current

    @property
    def success(self):
        return self.value == self.end

    def reset(self):
        """Reset timer to start value"""
        self.value = self.start
        self.active = True

        if callable(self.on_reset):
            self.on_reset()

    def stop(self):
        """Stop timer updating"""
        self.value = self.end
        self.active = False

        if callable(self.on_stop):
            self.on_stop()

        if self.disposable:
            self.delete()

    def update(self, delta_time):
        """Update timer value

        :param delta_time: time since last update
        """
        if not self.active:
            return

        self.value = self.update_operator(self.value, delta_time)

        if callable(self.on_update):
            self.on_update()

        if self.comparison_operator(self.value, self.end):

            if callable(self.on_target):
                self.on_target()

            if self.repeat:
                self.reset()

            else:
                self.stop()


class Timer(ManualTimer, SignalListener):
    """Managed timer class with callbacks"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.register_signals()

    def delete(self):
        """Unregister timer signals"""
        self.unregister_signals()

    @TimerUpdateSignal.on_global
    def update(self, delta_time):
        super().update(delta_time)
