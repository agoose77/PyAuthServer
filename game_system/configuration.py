from collections import OrderedDict

from .configobj import ConfigObj

__all__ = ["load_keybindings"]


def load_keybindings(filepath, section_name, input_codes):
    """Load keybindings from config file

    :param filepath: path to config file
    :param section_name: name of keybindings section
    :param input_fields: permitted keybinding field names
    :param input_codes: mapping of names to code values
    :returns: dictionary of name to input codes
    """
    # Load into parser
    parser = ConfigObj(filepath)
    parser['DEFAULT'] = input_codes
    parser_result = parser[section_name]

    return {name: int(binding) for name, binding in parser_result.items()}