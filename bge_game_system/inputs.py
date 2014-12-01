from game_system.enums import InputEvents

from bge import events
from inspect import getmembers

__all__ = ['convert_from_bge_event']

bge_events = {v: k for k, v in getmembers(events)}


def convert_from_bge_event(event):
    """Parse a BGE event code and return InputEvent value

    :param event: BGE event
    """
    name = bge_events[event]
    return getattr(InputEvents, name)