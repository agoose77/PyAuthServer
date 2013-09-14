from operator import (add as add_func, sub as sub_func,
                      lt as less_func, gt as more_func)


class Timer:

    def __init__(self, target_value=0.0, initial_value=0.0,
                 count_down=False, on_target=None):
        self.target = target_value
        self.update_operator = sub_func if count_down else add_func
        self.comparison_operator = less_func if count_down else more_func
        self.callback = on_target
        self.value = 0.0

    def update(self, delta_time):
        self.value = self.update_operator(self.value, delta_time)
        if self.comparison_operator(self.value, self.target):
            if callable(self.callback):
                self.callback()
