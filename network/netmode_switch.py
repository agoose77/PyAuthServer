from .type_register import TypeRegister
from .world_info import WorldInfo

__all__ = ['NetmodeSwitch']


class NetmodeSwitch(metaclass=TypeRegister):

    @classmethod
    def find_subclass_for(cls, netmode):
        for subcls in cls.subclasses.values():

            if getattr(subcls, "_netmode") == netmode:
                return subcls

        raise TypeError("Netmode {} is not supported by this class"
                        .format(netmode))

    def __new__(cls, *args, **kwargs):
        specific_cls = cls.find_subclass_for(WorldInfo.netmode)

        return super().__new__(specific_cls)
