from network.signals import Signal


__all__ = ["UIWeaponDataChangedSignal", "UIWeaponChangedSignal", "UIHealthChangedSignal", "TeamSelectionQuerySignal",
           "TeamSelectionUpdatedSignal"]


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
