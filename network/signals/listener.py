from inspect import getmembers

from ..conditions import is_annotatable, is_signal_listener
from ..structures import factory_dict
from ..signals import Signal

__all__ = "SignalListener",


def members_predicate(member):
    return is_annotatable(member) and is_signal_listener(member)


def create_signals_cache(cls):
    """Callback to register decorated functions for signals

    :param cls: Class to inspect for cache
    """
    signal_names = cls.lookup_dict[cls] = [name for name, val in getmembers(cls, members_predicate)]
    return signal_names


class SignalListener:
    """Provides interface for class based signal listeners.

    Uses class instance as target for signal binding.

    Optional greedy binding (binds the events supported by either class).
    """

    lookup_dict = factory_dict(create_signals_cache)

    @property
    def signal_callbacks(self):
        """Gets the marked signal callbacks

        :return: generator of (name, attribute) pairs
        """
        for name in self.lookup_dict[self.__class__]:
            yield name, getattr(self, name)

    def register_child(self, child, signal_store=None, greedy=False):
        """Subscribes child to parent for signals

        :param child: child to subscribe for
        :param signal_store: SignalListener subclass instance, default=None
        :param greedy: determines if child should bind its own events, default=False
        """
        # Mirror own signals by default
        if signal_store is None:
            signal_store = self

        for _, callback in signal_store.signal_callbacks:
            for signal, *_ in Signal.get_signals(callback):
                signal.set_parent(child, self)

        # Register child's signals as well as parents
        if greedy:
            self.register_child(child, signal_store=child)

    def unregister_child(self, child, signal_store=None, greedy=False):
        """Unsubscribe the child to parent for signals

        :param child: Child to be unsubscribed
        :param signal_store: SignalListener subclass instance, default=None
        :param greedy: determines if child should un-bind its own events,
        default=False
        """
        # Mirror own signals by default
        if signal_store is None:
            signal_store = self

        for _, callback in signal_store.signal_callbacks:
            for signal, *_ in Signal.get_signals(callback):
                signal.remove_parent(child, self)

        # Unregister child's signals as well as parents
        if greedy:
            self.unregister_child(child, child)

    def register_signals(self):
        """Register signals to observer"""
        for _, callback in self.signal_callbacks:
            Signal.subscribe(self, callback)

    def unregister_signals(self):
        """Unregister signals from observer"""
        for _, callback in self.signal_callbacks:
            Signal.unsubscribe(self, callback)