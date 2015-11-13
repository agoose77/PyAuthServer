from functools import lru_cache
from inspect import getmembers

from ..annotations.conditions import is_annotatable
from ..annotations.decorators import get_annotation, set_annotation


__all__ = 'on_protocol', 'send_for_state'

on_protocol = set_annotation("on_protocol")
send_for_state = set_annotation("send_for_state")


def _find_with_annotation(cls, annotation):
    functions = {}

    getter = get_annotation(annotation)
    for name, func in getmembers(cls, is_annotatable):
        value = getter(func)
        if value is not None:
            functions[value] = func

    return functions


@lru_cache()
def _get_unbound_listeners(cls):
    return _find_with_annotation(cls, "on_protocol")


def register_protocol_listeners(stream, messenger):
    unbound_listeners = _get_unbound_listeners(stream.__class__)

    for protocol, listener in unbound_listeners.items():
        func = listener.__get__(stream)
        messenger.add_subscriber(protocol, func)


@lru_cache()
def _get_unbound_state_senders(cls):
    return _find_with_annotation(cls, "send_for_state")


def get_state_senders(stream):
    unbound_senders = _get_unbound_state_senders(stream.__class__)
    return {state: sender.__get__(stream) for state, sender in unbound_senders.items()}