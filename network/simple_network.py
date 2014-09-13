from .replicable import Replicable
from .network import Network
from .connection import Connection
from .world_info import WorldInfo
from .signals import Signal

from time import clock

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

        WorldInfo.register(instance_id=WorldInfo.instance_id, immediately=True)
        Signal.update_graph()
        
        if callable(self.on_initialised):
            self.on_initialised()

        started = clock()
        last_time = started

        while True:
            current_time = clock()
            if (current_time - last_time) < update_rate:
                continue

            last_time = current_time
            
            any_connections = bool(Connection)

            if timeout is None:
                timed_out = False

            else:
                timed_out = (current_time - started) > timeout

            if not any_connections and timed_out:
                break
             
            self.step()

        if callable(self.on_finished):
            self.on_finished()

        self.stop()


def respect_interval(interval, function):
    """Decorator to ensure function is only called after a minimum interval

    :param interval: minimum interval between successive calls
    :param function: function to call
    """
    def wrapper():
        last_called = clock()

        while True:
            now = clock()
            dt = now - last_called

            if dt >= interval:
                function()
                last_called = now

            yield

    return wrapper().__next__