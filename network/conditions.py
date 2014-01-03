def is_reliable(func):
    return func.__annotations__.get("reliable", False)


def is_simulated(func):
    return func.__annotations__.get("simulated", False)


def is_signal_listener(func):
    return "signals" in func.__annotations__
