from .replicables import WorldInfo
from .type_register import TypeRegister

__all__ = ['NetmodeSwitch']


class NetmodeSwitch(metaclass=TypeRegister):

    @classmethod
    def netmode_specific(cls, id_):
        netmode_classes = (t for t in cls.subclasses.values() if
                           getattr(t, "_netmode_data") == (t, id_))

        try:
            return next(netmode_classes)

        except StopIteration as err:
            raise TypeError("Netmode is not supported by this class") from err

    def __new__(cls, *args, **kwargs):
        specific_cls = cls.netmode_specific(WorldInfo.netmode)

        return super().__new__(specific_cls)
