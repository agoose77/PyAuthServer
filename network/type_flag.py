__all__ = ["TypeFlag"]


class TypeFlag:
    """Container for static type information.

    Holds type for value and additional keyword arguments.

    Pretty printable.
    """
    __slots__ = ['data_type', 'data']

    def __init__(self, data_type, **kwargs):
        self.data_type = data_type
        self.data = kwargs

    def __repr__(self):
        return "<TypeFlag: type={}>".format(self.data_type)
