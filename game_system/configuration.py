from .configobj import ConfigObj

__all__ = ["load_keybindings"]


def load_keybindings(file_path, names_to_codes):
    """Load keybindings from config file

    :param file_path: path to config file
    :param names_to_codes: mapping of names to code values
    :returns: dictionary of name to input codes
    """
    # Load into parser
    parser = ConfigObj(file_path)
    parser['DEFAULT'] = names_to_codes

    return {name: int(binding) for name, binding in parser.items()}