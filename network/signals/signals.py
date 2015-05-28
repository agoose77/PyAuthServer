from collections import defaultdict
from inspect import signature
from functools import wraps

from ..logger import logger
from ..decorators import signal_listener
from ..descriptors import ContextMember
from ..metaclasses.register import TypeRegister
from ..metaclasses.context import ContextMemberMeta


__all__ = ('SignalMeta', 'Signal', 'ReplicableRegisteredSignal', 'ReplicableUnregisteredSignal',
           'ConnectionErrorSignal', 'ConnectionSuccessSignal', 'SignalValue',  'DisconnectSignal',
           'ConnectionDeletedSignal', 'LatencyUpdatedSignal', 'ConnectionTimeoutSignal')


class SignalMeta(TypeRegister, ContextMemberMeta):

    subscribers = ContextMember({})
    isolated_subscribers = ContextMember({})
    children = ContextMember({})

    @property
    def current_context_manager(cls):
        return cls._current_context_manager

    @current_context_manager.setter
    def current_context_manager(cls, context_manager):
        cls._current_context_manager = context_manager

        # Apply for all subclasses
        context_member_data = context_manager.data
        for sub_cls in cls.subclasses.values():
            sub_cls.context_member_data = context_member_data[sub_cls]

    def get_default_context(cls):
        """Return default context data for this class, for new context managers"""
        return {sub_cls: {} for sub_cls in cls.subclasses.values()}

    def merge_context(cls, context):
        """Merge other context with current context.

        Returns current context manager
        """
        current_context_manager = cls.current_context_manager

        context_member_data = current_context_manager.data
        for sub_cls, other_context_member_data in context.data.items():
            try:
                current_data = context_member_data[sub_cls]

            except KeyError:
                current_data = context_member_data[sub_cls] = {}

            current_data.update(other_context_member_data)
            other_context_member_data.clear()

        return current_context_manager


class Signal(metaclass=SignalMeta):
    """Observer class for signal-like invocation"""
    subclasses = {}

    @classmethod
    def register_base_class(cls):
        cls.register_subclass()
        cls.highest_signal = cls

    @classmethod
    def register_subclass(cls):
        cls.context_member_data = {}

    @staticmethod
    def get_signals(decorated):
        return decorated.__annotations__['signals']

    @classmethod
    def set_parent(cls, child_identifier, parent_identifier):
        children = cls.children

        try:
            children = children[parent_identifier]

        except KeyError:
            children = children[parent_identifier] = set()

        children.add(child_identifier)

    @classmethod
    def remove_parent(cls, child_identifier, parent_identifier):
        children = cls.children
        parent_children_dict = children[parent_identifier]
        # Remove from parent's children
        parent_children_dict.remove(child_identifier)
        # If we are the last child, remove parent
        if not parent_children_dict:
            children.pop(parent_identifier)

    @classmethod
    def get_total_subscribers(cls):
        return len(cls.subscribers) + len(cls.isolated_subscribers)

    @staticmethod
    def bind_callback(callback):
        parameters = signature(callback).parameters

        bind_signal = "signal" in parameters
        accept_target = "target" in parameters

        if accept_target:
            if bind_signal:
                def wrapper(*args, target, signal, **kwargs):
                    try:
                        callback(*args, target=target, signal=signal, **kwargs)
                    except Exception:
                        print(callback)
                        raise

            else:
                def wrapper(*args, target, signal, **kwargs):
                    callback(*args, target=target, **kwargs)

        else:
            if bind_signal:
                def wrapper(*args, target, signal, **kwargs):
                    callback(*args, signal=signal, **kwargs)
            else:
                def wrapper(*args, target, signal, **kwargs):
                    callback(*args, **kwargs)

        return wraps(callback)(wrapper)

    @classmethod
    def unsubscribe(cls, identifier, callback):
        """Unsubscribe from this Signal class

        :param identifier: identifier used to subscribe
        :param callback: callback that was used to subscribe
        """
        signals_data = cls.get_signals(callback)

        for signal_cls, is_context in signals_data:
            if is_context:
                callbacks = signal_cls.isolated_subscribers[identifier]
                callbacks.pop(callback)

                if not callbacks:
                    signal_cls.isolated_subscribers.pop(identifier)

            else:
                signal_cls.subscribers.pop(callback)

            signal_children = signal_cls.children

            # Remove parent from children
            if identifier in signal_children:
                for child in list(signal_children[identifier]):
                    signal_cls.remove_parent(child, identifier)

            # Remove from parents if a child
            for parent, next_children in list(signal_children.items()):
                if identifier in next_children:
                    signal_cls.remove_parent(identifier, parent)

    @classmethod
    def subscribe(cls, identifier, callback):
        """Subscribe to this Signal class using an identifier handle and a callback when invoked

        :param identifier: identifier for recipient of signal
        :param callback: callable to run when signal is invoked
        """
        signals_data = cls.get_signals(callback)
        bound_callback = cls.bind_callback(callback)

        for signal_cls, is_context in signals_data:
            if is_context:
                try:
                    callbacks = signal_cls.isolated_subscribers[identifier]

                except KeyError:
                    callbacks = signal_cls.isolated_subscribers[identifier] = {}

                callbacks[callback] = bound_callback

            else:
                signal_cls.subscribers[callback] = bound_callback

    @classmethod
    def invoke_targets(cls, target_dict, signal, target, args, kwargs, addressee=None):
        """Invoke signals for targeted recipient.

        If recipient has children, invoke them as well.

        Children do not require parents to listen for the signal.

        :param target_dict: mapping from on_context to on_context information
        :param target: target referred to by Signal invocation
        :param addressee: Recipient of Signal invocation (parent of child
        tree by default)
        :param *args: tuple of additional arguments
        :param **kwargs: dict of additional keyword arguments
        """
        if addressee is None:
            addressee = target

        # If the child is a context on_context
        if addressee in target_dict:
            callbacks = target_dict[addressee]

            for callback in callbacks.values():
                # Invoke with the same signal context even if this is a child
                try:
                    callback(*args, target=target, signal=signal, **kwargs)

                except Exception:
                    logger.exception("Unable to invoke Signal {}".format(signal))

        # Update children of this on_context
        if addressee in cls.children:
            for target_child in list(cls.children[addressee]):
                cls.invoke_targets(target_dict, signal, target, args, kwargs, addressee=target_child)

    @classmethod
    def invoke_general(cls, subscriber_dict, signal, target, args, kwargs):
        """Invoke signals for non targeted listeners

        :param subscriber_dict: mapping from subscriber identifier to callback
        :param target: target referred to by Signal invocation
        :param *args: tuple of additional arguments
        :param **kwargs: dict of additional keyword arguments
        """
        for callback in list(subscriber_dict.values()):
            try:
                callback(*args, target=target, signal=signal, **kwargs)

            except Exception:
                logger.exception("Unable to invoke Signal {}".format(signal))

    @classmethod
    def invoke(cls, *args, signal=None, target=None, **kwargs):
        """Invoke signals for a Signal type

        :param target: target referred to by Signal invocation
        :param *args: tuple of additional arguments
        :param **kwargs: dict of additional keyword arguments
        """
        if signal is None:
            signal = cls

        if target:
            cls.invoke_targets(cls.isolated_subscribers, signal, target, args, kwargs)

        cls.invoke_general(cls.subscribers, signal, target, args, kwargs)
        cls.invoke_parent(signal, target, args, kwargs)

    @classmethod
    def invoke_parent(cls, signal, target, args, kwargs):
        """Invoke signals for superclass of Signal type

        :param target: target referred to by Signal invocation
        :param *args: tuple of additional arguments
        :param **kwargs: dict of additional keyword arguments
        """
        if cls.highest_signal == cls:
            return

        try:
            parent = cls.__mro__[1]

        except IndexError:
            return

        parent.invoke(*args, signal=signal, target=target, **kwargs)

    @classmethod
    def on_global(cls, func):
        """Decorator for global signal listeners

        :param func: function to decorate
        :returns: passed function func
        """
        return signal_listener(cls, True)(func)

    @classmethod
    def on_context(cls, func):
        """Decorator for targeted signal listeners

        :param func: function to decorate
        :returns: passed function func
        """
        return signal_listener(cls, False)(func)


class SignalValue:
    """Container for signal callback return arguments"""

    __slots__ = '_value', '_changed', '_single_value'

    def __init__(self, default=None, single_value=False):
        self._single_value = single_value
        self._value = default
        self._changed = False

    @property
    def changed(self):
        return self._changed

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value):
        if self._single_value and self._changed:
            raise ValueError("Value already set")

        self._value = value
        self._changed = True

    def create_getter(self):
        """Create a getter function for the internal value"""
        def wrapper():
            return self.value

        return wrapper

    def create_setter(self, value):
        """Create a setter function for the internal value

        :param value: value to set when invoked
        """
        def wrapper():
            self.value = value

        return wrapper


class ReplicableRegisteredSignal(Signal):
    pass


class ReplicableUnregisteredSignal(Signal):
    pass


class DisconnectSignal(Signal):
    pass


class ConnectionTimeoutSignal(Signal):
    pass


class ConnectionErrorSignal(Signal):
    pass


class ConnectionSuccessSignal(Signal):
    pass


class ConnectionDeletedSignal(Signal):
    pass


class LatencyUpdatedSignal(Signal):
    pass
