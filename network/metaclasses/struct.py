from .mapping.attribute_mapping import AttributeMeta
from ..flag_serialiser import FlagSerialiser

__all__ = ['StructMeta']


class StructMeta(AttributeMeta):
    """Creates serialiser code for class (optimisation)"""

    def __new__(mcs, name, bases, cls_dict):
        cls = super().__new__(mcs, name, bases, cls_dict)

        attribute_container = cls._attribute_container
        factory_callback = attribute_container.callback
        ordered_arguments = factory_callback.keywords['ordered_mapping']

        cls._serialiser = FlagSerialiser(ordered_arguments)
        cls.__slots__ = ()

        return cls