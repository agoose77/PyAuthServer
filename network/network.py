from .connection_interfaces import ConnectionInterface
from .enums import ConnectionStatus

from socket import (socket, AF_INET, SOCK_DGRAM, error as socket_error)
from time import monotonic


class Network(socket):

    def __init__(self, addr, port, update_interval=1 / 20):
        '''Network socket initialiser'''
        super().__init__(AF_INET, SOCK_DGRAM)

        self.bind((addr, port))
        self.setblocking(False)

        self._interval = update_interval
        self._last_sent = 0.0
        self._started = monotonic()

        self.sent_bytes = 0
        self.received_bytes = 0

    @property
    def can_send(self):
        '''Determines if the socket can send
        Result according to time elapsed >= send interval'''
        return (monotonic() - self._last_sent) >= self._interval

    @property
    def send_rate(self):
        return (self.sent_bytes / (monotonic() - self._started))

    @property
    def receive_rate(self):
        return (self.received_bytes / (monotonic() - self._started))

    def stop(self):
        self.close()

    def sendto(self, *args, **kwargs):
        '''Overrides sendto method to record sent time'''
        result = super().sendto(*args, **kwargs)

        self.sent_bytes += result
        return result

    def recvfrom(self, buff_size=63553):
        '''A partial function for recvfrom
        Used in iter(func, sentinel)'''
        try:
            return super().recvfrom(buff_size)
        except socket_error:
            return

    def receive(self):
        '''Receive all data from socket'''
        # Get connections
        get_connection = ConnectionInterface.get_from_graph

        # Receives all incoming data
        for bytes_, addr in iter(self.recvfrom, None):
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

    def send(self):
        '''Send all connection data and update timeouts'''
        # A switch between emergency and normal
        network_tick = self.can_send

        # Get connections
        to_delete = []

        send_func = self.sendto

        # Send all queued data
        for connection in ConnectionInterface:

            # If the connection should be removed (timeout or explicit)
            if connection.status < ConnectionStatus.disconnected:
                connection.request_unregistration()
                continue

            # Give the option to send nothing
            data = connection.send(network_tick)

            # If returns data, send it
            if data:
                send_func(data, connection.instance_id)

        if network_tick:
            self._last_sent = monotonic()

        # Delete dead connections
        ConnectionInterface.update_graph()

    def connect_to(self, conn, *args, **kwargs):
        return ConnectionInterface(conn, *args, **kwargs)
