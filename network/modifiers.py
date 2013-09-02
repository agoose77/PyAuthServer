def reliable(func):
    func.__annotations__['reliable'] = True
    return func


def simulated(func):
    func.__annotations__['simulated'] = True
    return func


def is_reliable(func):
    return func.__annotations__.get("reliable", False)


def is_simulated(func):
    return func.__annotations__.get("simulated", False)

