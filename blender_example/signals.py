from bge_network import Signal, BroadcastMessage


class ConsoleMessage(BroadcastMessage):
    pass


class ConnectToSignal(Signal):
    pass


class UIWeaponDataChangedSignal(Signal):
    pass


class UIWeaponChangedSignal(Signal):
    pass


class UIHealthChangedSignal(Signal):
    pass
