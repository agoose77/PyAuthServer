utilities = ["clamp", "median", "lerp", "mean"]


def clamp(low, high, value):
    """Constrain value within limits

    :param low: lower bound
    :param high: upper bound
    :param value: unconstrained value
    :returns: constrained value
    """
    return min(high, max(low, value))


def lerp(a, b, factor):
    """Linear interpolation between two numbers

    :param a: first term
    :param b: second term
    :param factor: interpolation factor
    :returns: interpolated value
    """
    return a + (b - a) * clamp(0, 1, factor)


def mean(iterable):
    """Finds the mean of an iterable object

    :param iterable: iterable object
    :returns: mean of all terms
    """
    fixed = list(iterable)

    try:
        first = fixed[0]

    except IndexError as err:
        raise ValueError("Empty iterable") from err

    return sum(fixed[1:], first) / len(fixed)


def median(iterable):
    """Finds the median of an iterable object

    :param iterable: iterable object
    :returns: median of all terms
    """
    fixed = sorted(iterable)
    total = len(fixed)

    if total % 2:
        index = round(total / 2)
        return fixed[index]

    else:
        start_index = total // 2
        end_index = start_index + 1
        return (fixed[start_index] + fixed[end_index]) / 2