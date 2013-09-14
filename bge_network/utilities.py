def clamp(low, high, actual):
    return min(high, max(low, actual))


def falloff_fraction(origin, maximum, actual, effective):
    distance = (actual - origin).length

    # If in optimal range
    if distance <= effective:
        distance_fraction = 0

    elif distance > maximum:
        distance_fraction = 1

    # If we are beyond optimal range
    else:
        distance_fraction = (((distance - effective) ** 2)
                     / (maximum - effective) ** 2)

    return clamp(0, 1, (1 - distance_fraction))
