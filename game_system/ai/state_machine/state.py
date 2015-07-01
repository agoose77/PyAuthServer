class State:

    def __init__(self):
        self.manager = None

    def __repr__(self):
        return self.__class__.__name__

    def on_enter(self):
        pass

    def on_exit(self):
        pass
