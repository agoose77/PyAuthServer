from .replicables import WorldInfo
from .bitfield import BitField
from .connection import ClientConnection, ServerConnection
from .conversions import conversion
from .decorators import netmode_switch
from .descriptors import TypeFlag
from .enums import ConnectionStatus, Netmodes, Protocols
from .errors import NetworkError, ConnectionTimeoutError
from .signals import (ConnectionSuccessSignal, ConnectionErrorSignal)
from .handler_interfaces import get_handler
from .packet import Packet, PacketCollection
from .netmode_switch import NetmodeSwitch
from .instance_register import InstanceRegister

from collections import deque
from operator import eq as equals_operator
from time import monotonic

__all__ = ["ConnectionInterface", "ClientInterface", "ServerInterface"]


class ConnectionInterface(NetmodeSwitch, metaclass=InstanceRegister):
    """Interface for remote peer
    Mediates a connection instance between local and remote peer"""

    def on_initialised(self):
        # Maximum sequence number value
        self.sequence_max_size = 255 ** 2
        self.sequence_handler = get_handler(TypeFlag(int,
                                            max_value=self.sequence_max_size))

        # Number of packets to ack per packet
        self.ack_window = 32

        # BitField and bitfield size
        self.ack_bitfield = BitField(self.ack_window)
        self.ack_packer = get_handler(TypeFlag(BitField))

        # Additional data
        self.netmode_packer = get_handler(TypeFlag(int))
        self.error_packer = get_handler(TypeFlag(str))

        # Protocol unpacker
        self.protocol_handler = get_handler(TypeFlag(int))

        # Storage for packets requesting ack or received
        self.requested_ack = {}
        self.received_window = deque()

        # Current indicators of latest out/incoming sequence numbers
        self.local_sequence = 0
        self.remote_sequence = 0

        # Time out for connection before it is deleted
        self.time_out = 5
        self.last_received = monotonic()

        # Simple connected status
        self.status = ConnectionStatus.disconnected  # @UndefinedVariable

        # Maintains an actual connection
        self.connection = None

        # Estimate available bandwidth
        self.bandwidth = conversion(1, "Mb", "B")
        self.packet_growth = conversion(0.5, "KB", "B")
        self.tagged_throttle_sequence = None
        self.throttle_pending = False

        self.buffer = []

    def on_unregistered(self):
        """Unregistration callback"""
        if self.connection:
            self.connection.on_delete()

    @classmethod
    def by_status(cls, status, comparator=equals_operator):
        """Filter connections by status
        @param status: status query
        @param comparator: comparison callback for filter"""
        count = 0
        for interface in cls:
            if comparator(interface.status, status):
                count += 1
        return count

    @property
    def next_local_sequence(self):
        """Property
        @returns next local sequence identifier"""
        current_sequence = self.local_sequence
        self.local_sequence = (current_sequence + 1) if (current_sequence <
                                             self.sequence_max_size) else 0
        return self.local_sequence

    def set_time_out(self, delay):
        """Sets the time out for peer
        @param delay: delay until interface is timed out"""
        self.time_out = delay

    def sequence_more_recent(self, base, sequence):
        """Compares two sequence identifiers
        determines if one is greater than the other
        @param base: base sequence to compare against
        @param sequence: sequence tested against base"""
        half_seq = (self.sequence_max_size / 2)
        return (((base > sequence) and (base - sequence) <= half_seq)
            or ((sequence > base) and (sequence - base) > half_seq))

    def delete(self):
        """Sets connection state to deleted"""
        self.status = ConnectionStatus.deleted  # @UndefinedVariable

    def connected(self, *args, **kwargs):
        """Sets connection state to connected
        @param args: additional positional arguments
        @param kwargs: additional keyword arguments"""
        self.status = ConnectionStatus.connected  # @UndefinedVariable
        ConnectionSuccessSignal.invoke(target=self)

    def send(self, network_tick):
        """Pulls data from connection interfaces to send
        @param network_tick: if this is a network tick"""
        # Check for timeout
        if (monotonic() - self.last_received) > self.time_out:
            self.status = ConnectionStatus.timeout  # @UndefinedVariable

            err = ConnectionTimeoutError("Connection timed out")
            ConnectionErrorSignal.invoke(err, target=self)

        # Self-incrementing sequence property
        sequence = self.next_local_sequence

        # If we are waiting to detect when packets have been received for throttling
        if self.throttle_pending and self.tagged_throttle_sequence is None:
            self.tagged_throttle_sequence = sequence

        # If not connected setup handshake
        if self.status == ConnectionStatus.disconnected:  # @UndefinedVariable
            packet_collection = PacketCollection(self.get_handshake())
            self.status = ConnectionStatus.handshake

        # If connected send normal data
        elif self.status == ConnectionStatus.connected:  # @UndefinedVariable
            packet_collection = self.connection.send(network_tick,
                                                     self.bandwidth)

        # Don't send any data between states
        else:
            return

        # Include any re-send
        if self.buffer and 0:
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

        # Force bandwidth to grow (until throttled)
        self.bandwidth += self.packet_growth

        return b''.join(ack_info)

    def stop_throttling(self):
        """Stops updating metric for bandwith"""
        self.tagged_throttle_sequence = None
        self.throttle_pending = False

    def start_throttling(self):
        """Starts updating metric for bandwith"""
        self.bandwidth /= 2
        self.throttle_pending = True

    def receive(self, bytes_):
        """Handles received bytes from peer
        @param bytes_: data from peer"""
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
            sequence_ = ack_base - (index + 1)

            # If it was acked successfully
            flag = ack_bitfield[index]

            # If we are waiting for this packet, acknowledge it
            if (flag and sequence_ in requested_ack):
                requested_ack.pop(sequence_).on_ack()

                # Check throttling status
                if sequence_ == self.tagged_throttle_sequence:
                    self.stop_throttling()

        # Acknowledge the sequence of this packet about
        if ack_base in self.requested_ack:
            requested_ack.pop(ack_base).on_ack()

            # Check throttling status
            if ack_base == self.tagged_throttle_sequence:
                self.stop_throttling()

        # Dropped locals
        window_size = self.ack_window
        buffer = self.buffer
        missed_ack = False

        # Find packets we think are dropped and resend them
        considered_dropped = set(seq_ for seq_ in requested_ack if
                                 (sequence - seq_) >= window_size)
        # If the packet drops off the ack_window assume it is lost
        for sequence_ in considered_dropped:
            # Only reliable members asked to be informed if received/dropped
            reliable_collection = requested_ack.pop(sequence_).to_reliable()
            reliable_collection.on_not_ack()

            missed_ack = True
            buffer.append(reliable_collection)

        # Respond to network conditions
        if missed_ack and not self.throttle_pending:
            self.start_throttling()

        # Called for handshake protocol
        receive_handshake = self.receive_handshake

        # Call post-processed receive
        if self.status != ConnectionStatus.connected:  # @UndefinedVariable
            for member in packet_collection.members:

                if member.protocol > Protocols.request_auth:  # @UndefinedVariable @IgnorePep8
                    continue

                receive_handshake(member)

        else:
            self.connection.receive(packet_collection.members)


@netmode_switch(Netmodes.server)  # @UndefinedVariable
class ServerInterface(ConnectionInterface):

    def on_initialised(self):
        """Initialised callback"""
        super().on_initialised()

        self._auth_error = None

    def on_unregistered(self):
        if self.connection is not None:
            WorldInfo.rules.on_disconnect(self.connection.replicable)

        super().on_unregistered()

    def get_handshake(self):
        '''Creates a handshake packet
        Either acknowledges connection or sends error state'''
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
        """Receives a handshake packet
        Either proceeds to setup connection or stores the error"""
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


@netmode_switch(Netmodes.client)
class ClientInterface(ConnectionInterface):

    def get_handshake(self):
        '''Creates a handshake packet
        Sends netmode to server'''
        return Packet(protocol=Protocols.request_auth,
                      payload=self.netmode_packer.pack(WorldInfo.netmode),
                      reliable=True)

    def receive_handshake(self, packet):
        """Receives a handshake packet
        Either proceeds to setup connection or invokes the error"""
        protocol = packet.protocol

        if protocol == Protocols.auth_failure:
            err_data = packet.payload[self.error_packer.size(packet.payload):]
            err_type = self.error_packer.unpack_from(packet.payload)
            err_body = self.error_packer.unpack_from(err_data)
            err = NetworkError.from_type_name(err_type)

            ConnectionErrorSignal.invoke(err, target=self)
        else:
            # Get remote network mode
            netmode = self.netmode_packer.unpack_from(packet.payload)
            # If we did not have an error then we succeeded
            self.connection = ClientConnection(netmode)
            self.connected()
