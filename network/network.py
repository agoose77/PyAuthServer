from .connection import Connection
from .enums import Netmodes
from .streams import create_handshake_manager

from random import random
from socket import (socket, AF_INET, SOCK_DGRAM, error as SOCK_ERROR, gethostname, gethostbyname, SOL_IP,
                    IP_MULTICAST_IF, IP_ADD_MEMBERSHIP, IP_MULTICAST_TTL, IP_DROP_MEMBERSHIP, inet_aton)
from time import clock

__all__ = ['BaseTransport', 'UnreliableSocketWrapper', 'NetworkManager', 'NetworkMetrics']


class TransportBase:

    TransportEmptyError = None

    def close(self):
        raise NotImplementedError()

    def receive(self, buff_szie):
        raise NotImplementedError()

    def send(self, data, address):
        raise NotImplementedError()


class DefaultTransport(socket, TransportBase):
    """Non blocking socket class"""

    TransportEmptyError = SOCK_ERROR

    def __init__(self, addr, port):
        """Network socket initialiser"""
        super().__init__(AF_INET, SOCK_DGRAM)

        self.bind((addr, port))
        self.setblocking(False)

        self.address, self.port = self.getsockname()

    close = socket.close
    receive = socket.recvfrom
    send = socket.sendto


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
        # If this class doesn't have the data member, return from wrapped socket
        return getattr(self._socket, name)

    def update(self):
        current_time = clock()
        delay = self.latency

        # Find eligible data to send
        index = 0
        for index, (timestamp, *payload) in enumerate(self._buffer_out):
            if (current_time - timestamp) < delay:
                break

        # Shrink window to find pending outgoing data
        pending_send = self._buffer_out[:index]
        self._buffer_out[:] = self._buffer_out[index:]

        # Send the delayed data
        send = self._socket.sendto
        sent_bytes = 0

        for timestamp, args, kwargs in pending_send:
            sent_bytes += send(*args, **kwargs)

        self._last_sent_bytes += sent_bytes

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

        multicast_socket = BaseTransport("", port)

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


class NetworkManager:
    """Network management class"""

    def __init__(self, address, port, netmode, transport_cls=DefaultTransport):
        transport = transport_cls()
        self._transport = DefaultTransport(address, port)

        self.address = transport.address
        self.port = transport.port
        self.netmode = netmode

        self.metrics = NetworkMetrics()
        self.multicast = MulticastDiscovery()
        self.receive_buffer_size = 63553

        self.rules = None

    def __repr__(self):
        return "<Network Manager: {}:{}>".format(self.address, self.port)

    def connect_to(self, address, port):
        """Return connection interface to remote peer.

        If connection does not exist, create a new ConnectionInterface.

        :param address: address of remote peer
        :param port: port of remote peer
        """
        address = gethostbyname(address)
        return self._create_or_return_connection((address, port))

    def _create_or_return_connection(self, connection_info):
        try:
            return Connection[connection_info]

        except KeyError:
            connection = Connection(connection_info, self)

        self.on_new_connection(connection)
        return connection

    @property
    def received_data(self):
        """Return iterator over received data"""
        buff_size = self.receive_buffer_size
        on_received_bytes = self.metrics.on_received_bytes

        receive = self._transport.receive
        TransportEmptyError = self._transport.TransportEmptyError

        while True:
            try:
                address, data = receive(buff_size)

            except TransportEmptyError:
                return

            payload, _ = data
            on_received_bytes(len(data))

            yield data

    def on_new_connection(self, connection):
        connection.handshake_manager = create_handshake_manager(self.netmode, connection)

    def receive(self):
        """Receive all data from socket"""
        # Receives all incoming data
        for data, address in self.received_data:
            # Find existing connection for address
            connection = self._create_or_return_connection(address)

            # Dispatch data to connection
            connection.receive_message(data)

        # Update multi-cast listeners
        self.multicast.receive()

    def send(self, full_update):
        """Send all connection data and update timeouts

        :param full_update: whether this is a full send call
        """
        send_func = self.send_to

        # Send all queued data
        for connection in list(Connection):
            # Give the option to send nothing
            messages = connection.request_messages(full_update)

            # If returns data, send it
            for message in messages:
                send_func(message, connection.instance_id)

    def send_to(self, data, address):
        """Send data to remote peer

        :param data: data to send
        :param address: address of remote peer
        """
        data_length = self._transport.send(data, address)
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
        self._transport.close()
        self.multicast.stop()


def create_network_manager(world, address="", port=0):
    netmode = world.netmode
    return NetworkManager(address, port, netmode)
