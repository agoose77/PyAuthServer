from .connection import Connection
from .decorators import ignore_arguments
from .signals import SignalListener

from collections import deque
from socket import (socket, AF_INET, SOCK_DGRAM, error as SOCK_ERROR, gethostname, gethostbyname, SOL_IP,
                    IP_MULTICAST_IF, IP_ADD_MEMBERSHIP, IP_MULTICAST_TTL, IP_DROP_MEMBERSHIP, inet_aton)
from time import clock

__all__ = ['NonBlockingSocketUDP', 'UnreliableSocketUDP', 'Network', 'NetworkMetrics']


class NonBlockingSocketUDP(socket):
    """Non blocking socket class"""

    def __init__(self, addr, port):
        """Network socket initialiser"""
        super().__init__(AF_INET, SOCK_DGRAM)

        self.bind((addr, port))
        self.setblocking(False)


class UnreliableSocketUDP(SignalListener, NonBlockingSocketUDP):
    """Non blocking socket class.

    A SignalListener which applies artificial latency
    to outgoing packets
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.delay = 0.000
        self._buffer_out = deque()

    @ignore_arguments
    def delayed_send(self):
        current_time = clock()

        # Check if we can send delayed data
        delay = self.delay

        index = 0
        for index, (timestamp, *payload) in enumerate(self._buffer_out):
            if (current_time - timestamp) < delay:
                break

        pending_send = self._buffer_out[:index]
        self._buffer_out[:] = self._buffer_out[index:]

        # Send the delayed data
        send = super().sendto
        for timestamp, (args, kwargs) in pending_send:
            send(*args, **kwargs)

    def sendto(self, *args, **kwargs):
        # Store data for delay
        self._buffer_out.append((clock(), args, kwargs))
        return 0


class NetworkMetrics:
    """Metrics object for network transfers"""

    def __init__(self):
        self._delta_received = 0
        self._delta_sent = 0
        self._delta_timestamp = 0.0

        self._received_bytes = 0
        self._sent_bytes = 0

    @property
    def sent_bytes(self):
        return self._sent_bytes

    @property
    def received_bytes(self):
        return self._received_bytes

    @property
    def send_rate(self):
        return self._delta_sent / (clock() - self._delta_timestamp)

    @property
    def receive_rate(self):
        return self._delta_received / (clock() - self._delta_timestamp)

    @property
    def sample_age(self):
        return clock() - self._delta_timestamp

    def on_sent_bytes(self, sent_bytes):
        """Update internal sent bytes"""
        self._sent_bytes += sent_bytes
        self._delta_sent += sent_bytes

    def on_received_bytes(self, received_bytes):
        """Update internal received bytes"""
        self._received_bytes += received_bytes
        self._delta_received += received_bytes

    def reset_sample_window(self):
        """Reset data used to calculate metrics"""
        self._delta_timestamp = clock()
        self._delta_sent = self._delta_received = 0


class MulticastDiscovery:
    """Interface for multi-cast discovery"""

    DEFAULT_HOST = ('224.0.0.0', 1201)

    def __init__(self):
        self._socket = None
        self._host = None

        self.on_reply = None

        self.receive_buffer_size = 63553

    @property
    def is_listener(self):
        return self._socket is not None

    def enable_listener(self, multicast_host=None, time_to_live=1):
        """Allow this network peer to receive multicast data

        :param multicast_host: address, port of multicast group
        """
        if multicast_host is None:
            multicast_host = self.DEFAULT_HOST

        address, port = multicast_host
        intf = gethostbyname(gethostname())

        multicast_socket = NonBlockingSocketUDP("", port)

        multicast_socket.setsockopt(SOL_IP, IP_MULTICAST_IF, inet_aton(intf))
        multicast_socket.setsockopt(SOL_IP, IP_ADD_MEMBERSHIP,
                                    inet_aton(address) + inet_aton(intf))
        multicast_socket.setsockopt(SOL_IP, IP_MULTICAST_TTL, time_to_live)

        self._host = multicast_host
        self._socket = multicast_socket

    def disable_listener(self):
        """Stop this network peer from receiving multicast data"""
        address, port = self._host
        self._socket.setsockopt(SOL_IP, IP_DROP_MEMBERSHIP,
                                inet_aton(address) + inet_aton('0.0.0.0'))

        self._host = None
        self._socket = None

    def _on_reply(self, host):
        if callable(self.on_reply):
            self.on_reply(host)

    def receive(self):
        if not self.is_listener:
            return

        buff_size = self.receive_buffer_size

        while True:

            try:
                data = self._socket.recvfrom(buff_size)

            except SOCK_ERROR:
                return

            _, host = data
            self._on_reply(host)


class Network:
    """Network management class"""

    def __init__(self, address, port):
        self.metrics = NetworkMetrics()
        self.receive_buffer_size = 63553
        self._socket = NonBlockingSocketUDP(address, port)

        self.address = address
        self.port = port

        self.multicast = MulticastDiscovery()

    def __repr__(self):
        return "<Network Manager: {}:{}>".format(self.address, self.port)

    @property
    def received_data(self):
        """Return iterator over received data"""
        buff_size = self.receive_buffer_size
        on_received_bytes = self.metrics.on_received_bytes

        while True:
            try:
                data = self._socket.recvfrom(buff_size)

            except SOCK_ERROR:
                return

            payload, _ = data
            on_received_bytes(len(data))

            yield data

    @staticmethod
    def connect_to(peer_data):
        """Return connection interface to remote peer.

        If connection does not exist, create a new ConnectionInterface.

        :param peer_data: tuple of address, port of remote peer
        """
        return Connection.create_connection(*peer_data)

    def receive(self):
        """Receive all data from socket"""
        # Get connections
        get_connection = Connection.get_from_graph

        # Receives all incoming data
        for data, address in self.received_data:
            # Find existing connection for address

            try:
                connection = get_connection(address, only_registered=False)

            # Create a new interface to handle connection
            except LookupError:
                connection = Connection(address)

            # Dispatch data to connection
            connection.receive(data)

        # Update multi-cast listeners
        self.multicast.receive()

        # Apply any changes to the Connection interface
        Connection.update_graph()  # @UndefinedVariable

    def send(self, full_update):
        """Send all connection data and update timeouts

        :param full_update: whether this is a full send call
        """
        send_func = self.send_to

        # Send all queued data
        for connection in Connection:
            # Give the option to send nothing
            data = connection.send(full_update)

            # If returns data, send it
            if data:
                send_func(data, connection.instance_id)

        # Delete dead connections
        Connection.update_graph()

    def send_to(self, data, address):
        """Send data to remote peer

        :param data: data to send
        :param address: address of remote peer
        """
        data_length = self._socket.sendto(data, address)

        self.metrics.on_sent_bytes(data_length)
        return data_length

    def ping_multicast(self, multicast_host=None):
        """Send a ping to a multicast group

        :param multicast_host: (address, port) of multicast group
        """
        if self.multicast.is_listener:
            raise TypeError("Multicast listeners cannot send pings")

        if multicast_host is None:
            multicast_host = self.multicast.DEFAULT_HOST

        self.send_to(b'', multicast_host)

    def stop(self):
        """Close network socket"""
        self._socket.close()
