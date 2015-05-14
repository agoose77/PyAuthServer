from .connection import Connection

from random import random
from socket import (socket, AF_INET, SOCK_DGRAM, error as SOCK_ERROR, gethostname, gethostbyname, SOL_IP,
                    IP_MULTICAST_IF, IP_ADD_MEMBERSHIP, IP_MULTICAST_TTL, IP_DROP_MEMBERSHIP, inet_aton)
from time import clock

__all__ = ['NonBlockingSocketUDP', 'UnreliableSocketWrapper', 'Network', 'NetworkMetrics']


class NonBlockingSocketUDP(socket):
    """Non blocking socket class"""

    def __init__(self, addr, port):
        """Network socket initialiser"""
        super().__init__(AF_INET, SOCK_DGRAM)

        self.bind((addr, port))
        self.setblocking(False)


class UnreliableSocketWrapper:
    """Non blocking socket class.

    A SignalListener which applies artificial latency
    to outgoing packets
    """

    def __init__(self, socket_):
        self._socket = socket_

        self.latency = 0.250
        self.packet_loss_factor = 0.10

        self._buffer_out = []
        self._last_sent_bytes = 0

    def __getattr__(self, name):
        return getattr(self._socket, name)

    def update(self):
        current_time = clock()

        # Check if we can send delayed data
        delay = self.latency

        index = 0
        for index, (timestamp, *payload) in enumerate(self._buffer_out):
            if (current_time - timestamp) < delay:
                break

        pending_send = self._buffer_out[:index]
        self._buffer_out[:] = self._buffer_out[index:]

        # Send the delayed data
        send = self._socket.sendto
        sent_bytes = self._last_sent_bytes

        for timestamp, args, kwargs in pending_send:
            sent_bytes += send(*args, **kwargs)

        self._last_sent_bytes = sent_bytes

    def sendto(self, *args, **kwargs):
        # Send count from actual send call
        sent_bytes, self._last_sent_bytes = self._last_sent_bytes, 0

        # Store data for delay
        if random() <= self.packet_loss_factor:
            return sent_bytes

        self._buffer_out.append((clock(), args, kwargs))
        return sent_bytes


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
        if self.is_listener:
            return

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
        if not self.is_listener:
            return

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

    def stop(self):
        self.disable_listener()


class Network:
    """Network management class"""

    def __init__(self, address, port):
        self.socket = NonBlockingSocketUDP(address, port)

        self.address = address
        self.port = port

        self.metrics = NetworkMetrics()
        self.multicast = MulticastDiscovery()
        self.receive_buffer_size = 63553

    def __repr__(self):
        return "<Network Manager: {}:{}>".format(self.address, self.port)

    @property
    def received_data(self):
        """Return iterator over received data"""
        buff_size = self.receive_buffer_size
        on_received_bytes = self.metrics.on_received_bytes

        while True:
            try:
                data = self.socket.recvfrom(buff_size)

            except SOCK_ERROR:
                return

            payload, _ = data
            on_received_bytes(len(data))

            yield data

    @staticmethod
    def connect_to(address, port):
        """Return connection interface to remote peer.

        If connection does not exist, create a new ConnectionInterface.

        :param address: address of remote peer
        :param port: port of remote peer
        """
        return Connection.create_connection(address, port)

    def receive(self):
        """Receive all data from socket"""
        # Receives all incoming data
        for data, address in self.received_data:
            # Find existing connection for address

            try:
                connection = Connection[address]

            # Create a new interface to handle connection
            except KeyError:
                connection = Connection(address)

            # Dispatch data to connection
            connection.receive(data)

        # Update multi-cast listeners
        self.multicast.receive()

    def send(self, full_update):
        """Send all connection data and update timeouts

        :param full_update: whether this is a full send call
        """
        send_func = self.send_to

        # Send all queued data
        for connection in Connection:
            print(connection, list(Connection))
            # Give the option to send nothing
            data = connection.send(full_update)

            # If returns data, send it
            if data:
                send_func(data, connection.instance_id)

    def send_to(self, data, address):
        """Send data to remote peer

        :param data: data to send
        :param address: address of remote peer
        """
        data_length = self.socket.sendto(data, address)
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
        self.socket.close()

        self.multicast.stop()
