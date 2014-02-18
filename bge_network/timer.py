from operator import (add as add_func, sub as sub_func,
                      lt as less_func, gt as more_func)
from network import SignalListener, UpdateSignal


class ManualTimer:

    def __init__(self, target_value=0.0, initial_value=0.0,
                 count_down=False, on_target=None, on_update=None,
                 on_stop=None, on_reset=None, repeat=False, active=True):
        super().__init__()

        self.target = target_value
        self.initial = self.value = initial_value

        self.update_operator = sub_func if count_down else add_func
        self.comparison_operator = less_func if count_down else more_func

        self.on_target = on_target
        self.on_update = on_update
        self.on_stop = on_stop
        self.on_reset = on_reset

        self.repeat = repeat
        self.active = active

    def delete(self):
        del self.on_target
        del self.on_update
        del self.on_stop
        del self.on_reset

        self.active = False

    @property
    def progress(self):
        total = self.target - self.initial
        current = self.value - self.initial
        return (1 / total) * current

    @property
    def success(self):
        return self.value == self.target

    def reset(self):
        self.value = self.initial
        self.active = True

        if callable(self.on_reset):
            self.on_reset()

    def stop(self):
        self.value = self.target
        self.active = False

        if callable(self.on_stop):
            self.on_stop()

    def update(self, delta_time):
        if self.active:
            self.value = self.update_operator(self.value, delta_time)

            if callable(self.on_update):
                self.on_update()

        if self.comparison_operator(self.value, self.target):

            if callable(self.on_target):
                self.on_target()

            if self.repeat:
                self.reset()

            else:
                self.stop()


class Timer(ManualTimer, SignalListener):

    def delete(self):
        self.unregister_signals()

    @UpdateSignal.global_listener
    def update(self, delta_time):
        super().update(delta_time)
