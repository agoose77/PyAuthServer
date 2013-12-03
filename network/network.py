from .connection_interfaces import ConnectionInterface
from .enums import ConnectionStatus

from collections import deque
from socket import (socket, AF_INET, SOCK_DGRAM, error as socket_error)
from time import monotonic

from .signals import (SignalListener, NetworkSendSignal,
                     NetworkReceiveSignal)


class UnblockingSocket(socket):

    def __init__(self, addr, port):
        '''Network socket initialiser'''
        super().__init__(AF_INET, SOCK_DGRAM)

        self.bind((addr, port))
        self.setblocking(False)


class UnreliableSocket(UnblockingSocket, SignalListener):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.delay = 0.100

        self._buffer_out = deque()
        self._buffer_in = deque()

        self.register_signals()

    @NetworkSendSignal.global_listener
    def poll(self, delta_time):
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


class Network(SignalListener):

    def __init__(self, addr, port):
        '''Network socket initialiser'''
        super().__init__()

        self._started = 0.0

        self.sent_bytes = 0
        self.received_bytes = 0

        self.socket = UnblockingSocket(addr, port)

        self.register_signals()

    @property
    def send_rate(self):
        return (self.sent_bytes / (monotonic() - self._started))

    @property
    def receive_rate(self):
        return (self.received_bytes / (monotonic() - self._started))

    def stop(self):
        self.socket.close()

    def send_to(self, *args, **kwargs):
        '''Overrides send_to method to record sent time'''
        result = self.socket.sendto(*args, **kwargs)

        self.sent_bytes += result
        return result

    def receive_from(self, buff_size=63553):
        '''A partial function for receive_from
        Used in iter(func, sentinel)'''
        try:
            return self.socket.recvfrom(buff_size)

        except socket_error:
            return

    @NetworkReceiveSignal.global_listener
    def receive(self):
        '''Receive all data from socket'''
        # Get connections
        get_connection = ConnectionInterface.get_from_graph

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
            self.received_bytes += len(bytes_)

        # Apply any changes to the Connection interface
        ConnectionInterface.update_graph()

    @NetworkSendSignal.global_listener
    def send(self, full_update):
        '''Send all connection data and update timeouts'''
        send_func = self.send_to
        disconnected_state = ConnectionStatus.disconnected

        # Send all queued data
        for connection in ConnectionInterface:

            # If the connection should be removed (timeout or explicit)
            if connection.status < disconnected_state:
                connection.request_unregistration()
                continue

            # Give the option to send nothing
            data = connection.send(full_update)

            # If returns data, send it
            if data:
                send_func(data, connection.instance_id)

        # Delete dead connections
        ConnectionInterface.update_graph()

    @staticmethod
    def connect_to(peer_data, *args, **kwargs):
        return ConnectionInterface(peer_data, *args, **kwargs)
