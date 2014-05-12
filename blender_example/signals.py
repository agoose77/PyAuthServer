from bge_network import Signal


__all__ = ["ConnectToSignal", "UIWeaponDataChangedSignal", "UIWeaponChangedSignal",
           "UIHealthChangedSignal", "TeamSelectionQuerySignal", "TeamSelectionUpdatedSignal"]


class ConnectToSignal(Signal):
    pass


class UIWeaponDataChangedSignal(Signal):
    pass


class UIWeaponChangedSignal(Signal):
    pass


class UIHealthChangedSignal(Signal):
    pass


class TeamSelectionUpdatedSignal(Signal):
    pass


class TeamSelectionQuerySignal(Signal):
    pass
