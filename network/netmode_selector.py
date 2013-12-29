from .replicables import WorldInfo


class NetmodeSelector:
    _netmode_mapping = {}

    @classmethod
    def netmode_specific(cls, id_):
        return cls._netmode_mapping[id_]

    def __new__(cls, *args, **kwargs):
        specific_cls = cls.netmode_specific(WorldInfo.netmode)
        return super().__new__(specific_cls)
