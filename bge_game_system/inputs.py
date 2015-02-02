from game_system.enums import InputEvents

from bge import events

__all__ = ['convert_from_bge_event']

bge_events = {getattr(events, k): k for k in dir(events) if k.isupper()}


def convert_from_bge_event(event):
    """Parse a BGE event code and return InputEvent value

    :param event: BGE event
    """
    name = bge_events[event]
    return getattr(InputEvents, name)