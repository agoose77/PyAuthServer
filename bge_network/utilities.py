def clamp(low, high, actual):
    return min(high, max(low, actual))


def lerp(a, b, factor):
    return a + (b - a) * factor


def mean(iterable):
    fixed = list(iterable)

    try:
        first = fixed[0]

    except IndexError as err:
        raise ValueError("Empty iterable") from err

    return sum(fixed[1:], first) / len(fixed)


def falloff_fraction(origin, maximum, actual, effective):
    distance = (actual - origin).length

    # If in optimal range
    if distance <= effective:
        distance_fraction = 1

    elif distance > maximum:
        distance_fraction = 0

    # If we are beyond optimal range
    else:
        falloff_fraction = (((distance - effective) ** 2)
                             / (maximum - effective) ** 2)

        return clamp(0, 1, (1 - falloff_fraction))

    return distance_fraction


def progress_string(fraction, fidelity=10):
    return "[{}]".format(''.join(('|' if (i / fidelity) < \
                          fraction else ' ' for i in range(fidelity))))
