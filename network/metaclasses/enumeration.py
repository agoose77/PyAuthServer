__all__ = "EnumerationMeta",


class EnumerationMeta(type):
    """Metaclass for Enumerations in Python"""

    def __new__(metacls, name, parents, attributes):
        try:
            values = attributes['values']
        except KeyError:
            pass

        else:
            # Get settings
            get_index = (lambda x: 2 ** x if attributes.get('use_bits', False) else x)

            forward_mapping = {v: get_index(i) for i, v in enumerate(values)}
            reverse_mapping = {i: v for v, i in forward_mapping.items()}

            attributes.update(forward_mapping)
            attributes['keys_to_values'] = forward_mapping
            attributes['values_to_keys'] = reverse_mapping

        # Return new class
        return super().__new__(metacls, name, parents, attributes)

    def __getitem__(cls, value):
        # Add ability to lookup name
        return cls.values_to_keys[value]

    def __contains__(cls, index):
        return index in cls.values_to_keys

    def __repr__(cls):
        contents_string = '\n'.join("<{}: {}>".format(*mapping) for mapping in cls.keys_to_values.items())
        return "<Enumeration {}>\n{}\n".format(cls.__name__, contents_string)