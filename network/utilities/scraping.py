from collections import OrderedDict


class ScraperDict(dict):

    def __init__(self, condition):
        super().__init__()

        self.found_items = OrderedDict()
        self._condition = condition

    def __setitem__(self, name, value):
        if self._condition(value):
            self.found_items[name] = value

        else:
            super().__setitem__(name, value)
