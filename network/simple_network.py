from .network import NetworkManager
from .connection import Connection

from time import clock

__all__ = ["SimpleNetworkManager", "respect_interval"]


class SimpleNetworkManager(NetworkManager):

    """Simple network update loop"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.running = False

    def stop(self):
        self.running = False
        self.on_finished()
        super().stop()

    def step(self):
        self.receive()
        full_update = self.on_update()
        self.send(full_update)

    def run(self, timeout=None, update_rate=1/60):
        started = clock()
        last_time = started

        self.running = True

        while self.running:
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

        self.stop()

    def on_finished(self):
        pass

    def on_update(self):
        return True


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
