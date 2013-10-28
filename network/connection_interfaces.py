from .replicables import WorldInfo
from .bitfield import Bitfield
from .connection import ClientConnection, ServerConnection
from .descriptors import StaticValue
from .enums import ConnectionStatus, Netmodes, Protocols
from .errors import NetworkError, TimeoutError
from .events import (ConnectionSuccessEvent, ConnectionErrorEvent)
from .handler_interfaces import get_handler
from .packet import Packet, PacketCollection
from .instance_register import InstanceRegister

from collections import deque
from operator import eq as equals_operator
from socket import gethostbyname
from time import monotonic


class ConnectionInterface(metaclass=InstanceRegister):

    def __init__(self, instance_id):

        # Maximum sequence number value
        self.sequence_max_size = 255 ** 2
        self.sequence_handler = get_handler(StaticValue(int,
                                            max_value=self.sequence_max_size))

        # Number of packets to ack per packet
        self.ack_window = 32

        # Bitfield and bitfield size
        self.ack_bitfield = Bitfield(self.ack_window)
        self.ack_packer = get_handler(StaticValue(Bitfield))

        # Additional data
        self.netmode_packer = get_handler(StaticValue(int))
        self.error_packer = get_handler(StaticValue(str))

        # Protocol unpacker
        self.protocol_handler = get_handler(StaticValue(int))

        # Storage for packets requesting ack or received
        self.requested_ack = {}
        self.received_window = deque()

        # Current indicators of latest out/incoming sequence numbers
        self.local_sequence = 0
        self.remote_sequence = 0

        # Time out for connection before it is deleted
        self.time_out = 2
        self.last_received = monotonic()

        # Simple connected status
        self.status = ConnectionStatus.disconnected

        # Maintains an actual connection
        self.connection = None

        self.buffer = []

        # Maintenance info
        super().__init__(instance_id=instance_id, register=True)

    def __new__(cls, *args, **kwargs):
        """Constructor switch depending upon netmode"""
        if cls is ConnectionInterface:
            netmode = WorldInfo.netmode

            if netmode == Netmodes.server:
                return ServerInterface.__new__(ServerInterface,
                                               *args, **kwargs)

            elif netmode == Netmodes.client:
                return ClientInterface.__new__(ClientInterface,
                                               *args, **kwargs)
        else:
            return super().__new__(cls)

    def on_unregistered(self):

        if self.connection:
            self.connection.on_delete()

    @classmethod
    def by_status(cls, status, comparator=equals_operator):
        count = 0
        for interface in cls:
            if comparator(interface.status, status):
                count += 1
        return count

    @property
    def next_local_sequence(self):
        current_sequence = self.local_sequence
        self.local_sequence = (current_sequence + 1) if (current_sequence <
                                             self.sequence_max_size) else 0
        return self.local_sequence

    def set_time_out(self, delay):
        self.time_out = delay

    def sequence_more_recent(self, s1, s2):
        half_seq = (self.sequence_max_size / 2)
        return ((s1 > s2) and (s1 - s2) <= half_seq) or ((s2 > s1)
                                             and (s2 - s1) > half_seq)

    def delete(self):
        self.status = ConnectionStatus.deleted

    def connected(self, *args, **kwargs):
        self.status = ConnectionStatus.connected
        ConnectionSuccessEvent.invoke(target=self)

    def send(self, network_tick):

        # Check for timeout
        if (monotonic() - self.last_received) > self.time_out:
            self.status = ConnectionStatus.timeout

            err = TimeoutError("Connection timed out")
            ConnectionErrorEvent.invoke(err, target=self)

        # If not connected setup handshake
        if self.status == ConnectionStatus.disconnected:
            packets = self.get_handshake()
            self.status = ConnectionStatus.handshake

        # If connected send normal data
        elif self.status == ConnectionStatus.connected:
            packets = self.connection.send(network_tick)

        # Don't send any data between states
        else:
            return

        # Create a packet collection from data
        packet_collection = PacketCollection(packets)

        # Include any re-send
        if self.buffer:
            # Read buffer
            packet_collection += PacketCollection(self.buffer)
            # Empty buffer
            self.buffer.clear()

        # Create a bitfield using window config
        ack_bitfield = self.ack_bitfield

        # The last received sequence number and received list
        remote_sequence = self.remote_sequence
        received_window = self.received_window

        # Acknowledge all packets we've received
        for index in range(self.ack_window):
            packet_sqn = remote_sequence - (index + 1)

            if packet_sqn < 0:
                continue

            ack_bitfield[index] = packet_sqn in received_window

        # Self-incrementing sequence property
        sequence = self.next_local_sequence

        # Construct header information
        ack_info = [self.sequence_handler.pack(sequence),
                    self.sequence_handler.pack(remote_sequence),
                    self.ack_packer.pack(ack_bitfield)]

        # Store acknowledge request for reliable members of packet
        self.requested_ack[sequence] = packet_collection

        # Add user data after header
        packet_bytes = packet_collection.to_bytes()

        if packet_bytes:
            ack_info.append(packet_bytes)

        # Return as bytes
        return b''.join(ack_info)

    def receive(self, bytes_):
        # Get the sequence id
        sequence = self.sequence_handler.unpack_from(bytes_)
        bytes_ = bytes_[self.sequence_handler.size():]

        # Get the base value for the bitfield
        ack_base = self.sequence_handler.unpack_from(bytes_)
        bytes_ = bytes_[self.sequence_handler.size():]

        # Read the acknowledgement bitfield
        self.ack_packer.unpack_merge(self.ack_bitfield, bytes_)
        bytes_ = bytes_[self.ack_packer.size(bytes_):]

        # Recreate packet collection
        packet_collection = PacketCollection().from_bytes(bytes_)

        # Store the received time
        self.last_received = monotonic()

        # If we receive a newer foreign sequence, update our local record
        if self.sequence_more_recent(sequence, self.remote_sequence):
            self.remote_sequence = sequence

        # Add packet to received list
        self.received_window.append(sequence)

        # Limit received size
        if len(self.received_window) > self.ack_window:
            self.received_window.popleft()

        # Dictionary of packets waiting for acknowledgement
        requested_ack = self.requested_ack
        ack_bitfield = self.ack_bitfield

        # Iterate over ACK bitfield
        for index in range(self.ack_window):
            sequence = ack_base - (index + 1)

            # If it was acked successfully
            flag = ack_bitfield[index]

            # If we are waiting for this packet, acknowledge it
            if (flag and sequence in requested_ack):
                requested_ack.pop(sequence).on_ack()

        # Acknowledge the sequence of this packet about
        if ack_base in self.requested_ack:
            requested_ack.pop(ack_base).on_ack()

        # If the packet drops off the ack_window assume it is lost
        likely_dropped = [k for k in requested_ack.keys()
                          if (sequence - k) > self.ack_window]

        # Find packets we think are dropped and resend them
        for sequence in likely_dropped:
            # Only reliable members asked to be informed if received/dropped
            reliable_collection = requested_ack.pop(sequence).to_reliable()
            reliable_collection.on_not_ack()
            self.buffer.append(reliable_collection)

        # Called for handshake protocol
        receive_handshake = self.receive_handshake

        # Call post-processed receive
        if self.status != ConnectionStatus.connected:
            for member in packet_collection.members:

                if member.protocol > Protocols.request_auth:
                    continue

                receive_handshake(member)

        else:
            self.connection.receive(packet_collection.members)


class ServerInterface(ConnectionInterface):

    def on_initialised(self):
        self._auth_error = None

    def on_unregistered(self):
        WorldInfo.rules.on_disconnect(self.connection.replicable)

        super().on_unregistered()

    def get_handshake(self):
        '''Will only exist if invoked'''
        connection_failed = self.connection is None

        if connection_failed:

            if self._auth_error:
                # Send the error code
                err_name = self.error_packer.pack(
                                          type(self.auth_error).type_name)
                err_body = self.error_packer.pack(
                                          self._auth_error.args[0])

                # Yield a reliable packet
                return Packet(protocol=Protocols.auth_failure,
                              payload=err_name + err_body,
                              on_success=self.delete)

        else:
            # Send acknowledgement
            return Packet(protocol=Protocols.auth_success,
                          payload=self.netmode_packer.pack(WorldInfo.netmode),
                          on_success=self.connected)

    def receive_handshake(self, packet):
        # Unpack data
        netmode = self.netmode_packer.unpack_from(packet.payload)

        # Store replicable
        try:
            if self.connection is not None:
                raise NetworkError("Connection already in mediation")
            WorldInfo.rules.pre_initialise(self.instance_id, netmode)

        # If a NetworkError is raised store the result
        except NetworkError as err:
            self._auth_error = err

        else:
            self.connection = ServerConnection(netmode)
            returned_replicable = WorldInfo.rules.post_initialise(
                                                          self.connection)
            # Replicable is boolean false until registered
            # User can force register though!
            if returned_replicable is not None:
                self.connection.replicable = returned_replicable


class ClientInterface(ConnectionInterface):

    def get_handshake(self):
        return Packet(protocol=Protocols.request_auth,
                      payload=self.netmode_packer.pack(WorldInfo.netmode),
                      reliable=True)

    def receive_handshake(self, packet):
        protocol = packet.protocol

        if protocol == Protocols.auth_failure:
            err_data = packet.payload[self.error_packer.size(packet.payload):]
            err_type = self.error_packer.unpack_from(packet.payload)
            err_body = self.error_packer.unpack_from(err_data)
            err = NetworkError.from_type_name(err_type)

            ConnectionErrorEvent.invoke(err, target=self)

        # Get remote network mode
        netmode = self.netmode_packer.unpack_from(packet.payload)
        # Must be success
        self.connection = ClientConnection(netmode)
        self.connected()
