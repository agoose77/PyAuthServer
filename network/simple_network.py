from .replicable import Replicable
from .enums import ConnectionStatus
from .network import Network
from .connection import Connection
from .world_info import WorldInfo
from .signals import Signal

from time import monotonic

__all__ = ["SimpleNetwork", "respect_interval"]


class SimpleNetwork(Network):

    """Simple network update loop"""

    def __init__(self, address, port):
        super().__init__(address, port)

        self.on_initialised = None
        self.on_finished = None
        self.on_update = None

    def step(self):
        self.receive()
        Replicable.update_graph()
        Signal.update_graph()

        full_update = True

        on_update = self.on_update
        if callable(on_update):
            full_update = on_update()

        self.send(full_update)

    def start(self, timeout=None, update_rate=1/60):
        # Handle successive runs (initialisation)
        Connection.clear_graph()
        Replicable.clear_graph()
        Signal.update_graph()

        WorldInfo.request_registration(instance_id=WorldInfo.instance_id, register=True)
        Signal.update_graph()
        
        if callable(self.on_initialised):
            self.on_initialised()

        started = monotonic()
        now = started

        while True:
            _now = monotonic()
            if (_now - now) < update_rate:
                continue
            
            now = _now
            
            any_connected = bool(Connection.by_status(ConnectionStatus.connected))

            timed_out = False
            if timeout is not None:
                timed_out = (now - started) > timeout

            if not any_connected and timed_out:
                break
             
            self.step()

        if callable(self.on_finished):
            self.on_finished()

        self.stop()


def respect_interval(interval, function):
    def wrapper():
        last_called = monotonic()

        while True:
            now = monotonic()
            dt = now - last_called

            if dt >= interval:
                function()
                last_called = now

            yield

    return wrapper().__next__