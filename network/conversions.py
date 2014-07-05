import math


def x10(number):
    return 10 ** number

bits = {"b": 1, "B": 8}
prefixes = {"K": x10(3), "M": x10(6), "G": x10(9)}


def get_scalar(fmt):
    scalar_a = prefixes.get(fmt[0], 1)
    scalar_b = bits[fmt[0] if scalar_a == 1 else fmt[1]]
    return scalar_a * scalar_b


def conversion(value, from_fmt, to_fmt, round_to_int=True, round_func=math.ceil):
    try:
        from_scalar = get_scalar(from_fmt)
        to_scalar = get_scalar(to_fmt)

    except KeyError:
        raise TypeError("Converter could not convert {} to {}".format(from_fmt, to_fmt))

    result = value * (from_scalar / to_scalar)

    if round_to_int:
        result = int(round_func(result))

    return result
