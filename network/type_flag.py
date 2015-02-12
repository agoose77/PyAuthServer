__all__ = ["Pointer", "TypeFlag"]


class Pointer:
    """Pointer to member of object"""

    def __init__(self, qualname):
        self._qualname = qualname

    def __call__(self, obj):
        """Retrieve member from object

        :param obj: object to traverse
        """
        parts = self._qualname.split(".")

        for part in parts:
            obj = getattr(obj, part)

        return obj


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
