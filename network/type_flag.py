__all__ = ["TypeFlag"]


class TypeFlag:
    """Container for static type information.

    Holds type for value and additional keyword arguments.

    Pretty printable.
    """
    __slots__ = ['type', 'data']

    def __init__(self, type, **kwargs):
        self.type = type
        self.data = kwargs

    def __repr__(self):
        return "<TypeFlag: type={}>".format(self.type)
