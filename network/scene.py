from .metaclasses.register import InstanceRegister
from .replicable import Replicable
from .signals import Signal


class NetworkScene(metaclass=InstanceRegister):

    def __init__(self, name, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.name = name
        self.context = self.create_context(name)

    @staticmethod
    def create_context(name):
        replicable_context = Replicable.get_context_manager(name)
        signal_context = Signal.get_context_manager(name)
        return AggregateContext(replicable_context, signal_context)

    def __repr__(self):
        return "<NetworkScene '{}'>".format(self.name)


class AggregateContext:

    def __init__(self, *contexts):
        self.contexts = contexts

    def __enter__(self):
        for context in self.contexts:
            context.__enter__()

    def __exit__(self, *exc_details):
        for context in self.contexts:
            context.__exit__(*exc_details)

