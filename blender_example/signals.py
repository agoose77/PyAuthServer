from bge_network import Signal, BroadcastMessage


class ConsoleMessage(BroadcastMessage):
    pass


class ConnectToSignal(Signal):
    pass


class UIUpdateSignal(Signal):
    pass


class UIWeaponChangedSignal(Signal):
    pass
