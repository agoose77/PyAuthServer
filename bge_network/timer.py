from operator import (add as add_func, sub as sub_func,
                      lt as less_func, gt as more_func)
from network import EventListener, UpdateEvent


class ManualTimer:

    def __init__(self, target_value=0.0, initial_value=0.0,
                 count_down=False, on_target=None, repeat=False):

        self.target = target_value
        self.initial = self.value = initial_value

        self.update_operator = sub_func if count_down else add_func
        self.comparison_operator = less_func if count_down else more_func

        self.callback = on_target
        self.repeat = repeat

        self.active = True

    def reset(self):
        self.value = self.initial

    def stop(self):
        self.value = self.target
        self.active = False

    def update(self, delta_time):
        if self.active:
            self.value = self.update_operator(self.value, delta_time)

        if self.comparison_operator(self.value, self.target):

            if callable(self.callback):
                self.callback()

            if self.repeat:
                self.reset()

            else:
                self.stop()


class Timer(ManualTimer, EventListener):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.listen_for_events()

    @UpdateEvent.global_listener
    def update(self, delta_time):
        super().update(delta_time)
