from network.structures import factory_dict
from game_system.enums import InputEvents

from bge import logic, events
from inspect import getmembers

__all__ = ['bge_status_lookup', 'convert_to_bge_event', 'get_dict_containing_events']


def get_dict_containing_events(event):
    """Return the events dictionary for the host device for an event type

    :param event: BGE event
    """
    keyboard = logic.keyboard
    return keyboard if event in keyboard.events else logic.mouse


def get_event_code(event_name):
    return getattr(events, event_name)


event_manager = factory_dict(get_dict_containing_events)
event_map = factory_dict(get_event_code)
bge_events = {v: k for k, v in getmembers(events)}


def convert_from_bge_event(event):
    """Parse a BGE event code and return InputEvent value

    :param event: BGE event
    """
    name = bge_events[event]
    return getattr(InputEvents, name)


def convert_to_bge_event(event):
    """Parse an InputEvent and return BGE event code

    :param event: :py:code:`bge_game_system.enums.InputEvent` code
    """
    try:
        event_name = InputEvents[event]

    except KeyError:
        raise ValueError("No such event {} is supported by this library".format(event))

    try:
        return event_map[event_name]

    except AttributeError as err:
        raise LookupError("No event with name {} was found in platform event list".format(event_name)) from err


def bge_status_lookup(event):
    """BGE interface for Input Status lookups

    :param event: :py:code:`bge_game_system.enums.InputEvent` code
    """
    bge_event = convert_to_bge_event(event)
    device_events = event_manager[bge_event].events
    return device_events[bge_event] in (logic.KX_INPUT_ACTIVE, logic.KX_INPUT_JUST_ACTIVATED)
