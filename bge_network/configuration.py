from inspect import getmembers
from bge import logic, events
from configparser import ConfigParser, ExtendedInterpolation
from collections import OrderedDict
from functools import partial


__all__ = ["load_keybindings"]


def load_keybindings(filepath, name, fields):
    """Load keybindings from config file

    :param filepath: path to config file
    :param name: name of class bindings belong to
    :param fields: named binding fields
    :returns: dictionary of name to input codes"""
    all_events = {name: str(value) for name, value in getmembers(events)
                  if isinstance(value, int)}
    filepath = logic.expandPath("//" + filepath)

    # Load into parser
    parser = ConfigParser(defaults=all_events,
                          interpolation=ExtendedInterpolation())
    parser.read(filepath)
    parser_result = parser[name]

    # Read binding information
    try:
        bindings = OrderedDict((field, int(parser_result[field]))
                                for field in fields)
    except KeyError as err:
        raise LookupError("Bindings are not defined for '{}'".format(name)) from err

    # Ensure we have all bindings
    if not set(fields).issubset(bindings):
        missing_bindings = ', '.join(set(fields).difference(bindings))
        raise ValueError("Some bindings were not defined: {}"
                         .format(missing_bindings))

    return bindings
