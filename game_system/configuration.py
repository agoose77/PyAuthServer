from configparser import ConfigParser, ExtendedInterpolation
from collections import OrderedDict

__all__ = ["load_keybindings"]


def load_keybindings(filepath, section_name, input_fields, input_codes):
    """Load keybindings from config file

    :param filepath: path to config file
    :param section_name: name of keybindings section
    :param input_fields: permitted keybinding field names
    :param input_codes: mapping of names to code values
    :returns: dictionary of name to input codes"""
    # Load into parser
    parser = ConfigParser(defaults=input_codes, interpolation=ExtendedInterpolation())
    parser.read(filepath)
    parser_result = parser[section_name]

    # Read binding information
    try:
        bindings = OrderedDict((field, int(parser_result[field])) for field in input_fields)

    except KeyError as err:
        raise LookupError("Bindings are not defined for '{}'".format(section_name)) from err

    # Ensure we have all bindings
    if not set(input_fields).issubset(bindings):
        missing_bindings = ', '.join(set(input_fields).difference(bindings))
        raise ValueError("Some bindings were not defined: {}".format(missing_bindings))

    return bindings
