from .replicables import WorldInfo

__all__ = ['NetmodeSwitch']


class NetmodeSwitch:

    @classmethod
    def netmode_specific(cls, id_):
        netmode_classes = (t for t in cls._types.values() if
                           getattr(t, "_netmode_data") == (t, id_))
        return next(netmode_classes)

    def __new__(cls, *args, **kwargs):
        specific_cls = cls.netmode_specific(WorldInfo.netmode)
        return super().__new__(specific_cls)
