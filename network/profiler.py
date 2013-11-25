from time import monotonic
from functools import wraps
from collections import defaultdict
from functools import partial

profiles = defaultdict(partial(defaultdict, int))


def profile(category):
    def wrapper(func):
        @wraps(func)
        def wrapper_(*args, **kwargs):
            start_time = monotonic()
            result = func(*args, **kwargs)
            end_time = monotonic()
            profiles[category][func.__qualname__ if hasattr(func, "__qualname__") else func.__name__] += end_time - start_time
        return wrapper_
    return wrapper
