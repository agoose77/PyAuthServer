from inspect import getmembers
from bge import logic, events
from configparser import ConfigParser, ExtendedInterpolation


def load_configuration(filepath, name, fields):
    all_events = {x[0]: str(x[1]) for x in getmembers(events)
                  if isinstance(x[1], int)}
    filepath = logic.expandPath("//" + filepath)

    # Load into parser
    parser = ConfigParser(defaults=all_events,
                          interpolation=ExtendedInterpolation())
    parser.read(filepath)

    # Read binding information
    bindings = {k: int(v) for k, v in parser[name].items()
            if not k.upper() in all_events and k in fields}

    # Ensure we have all bindings
    assert set(fields).issubset(bindings)
    return bindings
