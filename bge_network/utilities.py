import _ctypes

__all__ = ["clamp", "square_falloff", "lerp", "mean", "progress_string",
           "dereference_id"]


def clamp(low, high, value):
    '''Constrain value within limits

    :param low: lower bound
    :param high: upper bound
    :param value: unconstrained value
    :returns: constrained value'''
    return min(high, max(low, value))


def lerp(a, b, factor):
    '''Linear interpolation between two numbers

    :param a: first term
    :param b: second term
    :param factor: interpolation factor
    :returns: interpolated value'''
    return a + (b - a) * factor


def mean(iterable):
    '''Finds the mean of an iterable object

    :param iterable: iterable object
    :returns: mean of all terms'''
    fixed = list(iterable)

    try:
        first = fixed[0]

    except IndexError as err:
        raise ValueError("Empty iterable") from err

    return sum(fixed[1:], first) / len(fixed)


def square_falloff(source, target, maximum_distance, effective_distance):
    '''Determines scalar fall off from inputs
    Squares interpolation factor

    :param source: source position
    :param target: target position
    :param maximum_distance: upper bound to fall off
    :param effective_distance: lower bound for fall off
    :returns: squared fall off fraction'''
    distance = (target - source).length

    # If in optimal range
    if distance <= effective_distance:
        distance_fraction = 1

    elif distance > maximum_distance:
        distance_fraction = 0

    # If we are beyond optimal range
    else:
        square_falloff = (((distance - effective_distance) ** 2)
                             / (maximum_distance - effective_distance) ** 2)

        return clamp(0, 1, (1 - square_falloff))

    return distance_fraction


def progress_string(factor, fidelity=10):
    '''Creates a progress bar-like string

    :param factor: progress factor
    :param fidelity: number of characters used for progress
    :returns: progress bar like string [|||||     ]'''
    return "[{}]".format(''.join(('|' if (i / fidelity) < \
                          factor else ' ' for i in range(fidelity))))


def dereference_id(id_):
    return _ctypes.PyObj_FromPtr(id_)
