from .connection_interfaces import ConnectionInterface
from .enums import ConnectionStatus

from collections import deque
from socket import (socket, AF_INET, SOCK_DGRAM, error as socket_error)
from time import monotonic

from . import signals

__all__ = ['UDPSocket', 'UnreliableSocket', 'Network']


class UDPSocket(socket):
    """Non blocking socket class"""

    def __init__(self, addr, port):
        '''Network socket initialiser'''
        super().__init__(AF_INET, SOCK_DGRAM)

        self.bind((addr, port))
        self.setblocking(False)


class UnreliableSocket(signals.SignalListener, UDPSocket ):
    """Non blocking socket class
    A SignalListener which applies artificial latency
    to outgoing packets"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.delay = 0.000

        self._buffer_out = deque()
        self._buffer_in = deque()

    @signals.UpdateSignal.global_listener
    def cb(self, dt):
        self.poll()

    def poll(self):
        systime = monotonic()
        sendable = []

        # Check if we can send delayed data
        for data in self._buffer_out:
            if (systime - data[0]) >= self.delay:
                sendable.append(data)

        # Send the delayed data
        for data in sendable:
            self._buffer_out.remove(data)

            args_, kwargs_ = data[1:]
            super().sendto(*args_, **kwargs_)

    def sendto(self, *args, **kwargs):
        # Store data for delay
        self._buffer_out.append((monotonic(), args, kwargs))
        return 0


class Network:
    """Network management class"""

    def __init__(self, addr, port):
        '''Network socket initialiser'''
        super().__init__()

        self._delta_timestamp = 0.0

        self._delta_received = 0
        self._delta_sent = 0

        self.sent_bytes = 0
        self.received_bytes = 0

        self.socket = UnreliableSocket(addr, port)

    @property
    def send_rate(self):
        return (self.delta_sent / (monotonic() - self._delta_timestamp))

    @property
    def receive_rate(self):
        return (self.delta_received / (monotonic() - self._delta_timestamp))

    def reset_metrics(self):
        self._delta_timestamp = monotonic()
        self._delta_sent = self._delta_received = 0

    def stop(self):
        self.socket.close()

    def send_to(self, *args, **kwargs):
        '''Overrides send_to method to record sent time'''
        result = self.socket.sendto(*args, **kwargs)

        self.sent_bytes += result
        self._delta_sent += result

        return result

    def receive_from(self, buff_size=63553):
        '''A partial function for receive_from
        Used in iter(func, sentinel)'''
        try:
            return self.socket.recvfrom(buff_size)

        except socket_error:
            return

    def receive(self):
        '''Receive all data from socket'''
        # Get connections
        get_connection = ConnectionInterface.get_from_graph  # @UndefinedVariable @IgnorePep8

        # Receives all incoming data
        for bytes_, addr in iter(self.receive_from, None):
            # Find existing connection for address
            try:
                connection = get_connection(addr)

            # Create a new interface to handle connection
            except LookupError:
                connection = ConnectionInterface(addr)

            # Dispatch data to connection
            connection.receive(bytes_)

            # Update metrics
            byte_length = len(bytes_)
            self.received_bytes += byte_length
            self._delta_received += byte_length

        # Apply any changes to the Connection interface
        ConnectionInterface.update_graph()  # @UndefinedVariable

    def send(self, full_update):
        '''Send all connection data and update timeouts'''
        send_func = self.send_to
        pending_state = ConnectionStatus.pending  # @UndefinedVariable @IgnorePep8

        # Send all queued data
        for connection in ConnectionInterface:

            # If the connection should be removed (timeout or explicit)
            if connection.status < pending_state:
                connection.request_unregistration()
                continue

            # Give the option to send nothing
            data = connection.send(full_update)

            # If returns data, send it
            if data:
                send_func(data, connection.instance_id)

        # Delete dead connections
        ConnectionInterface.update_graph()  # @UndefinedVariable

    @staticmethod
    def connect_to(peer_data):
        try:
            return ConnectionInterface.get_from_graph(peer_data)

        except LookupError:
            return ConnectionInterface(peer_data)
