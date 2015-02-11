__all__ = ["TypeFlag"]


class FromClass:

    def __init__(self, qual_name):
        self._qual_name = qual_name

    def evaluate(self, base):
        parts = self._qual_name.split(".")

        for part in parts:
            base = getattr(base, part)

        return base


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
