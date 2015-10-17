from functools import wraps


def weak_method(obj, func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        return func.__get__(obj())(*args, **kwargs)

    return wrapper
