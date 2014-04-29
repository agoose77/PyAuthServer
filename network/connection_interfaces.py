from .bitfield import BitField
from .connection import Connection
from .conversions import conversion
from .decorators import netmode_switch, ignore_arguments
from .descriptors import TypeFlag
from .enums import ConnectionStatus, Netmodes, Protocols, HandshakeState
from .errors import NetworkError, ConnectionTimeoutError
from .handler_interfaces import get_handler
from .instance_register import InstanceRegister
from .netmode_switch import NetmodeSwitch
from .packet import Packet, PacketCollection
from .signals import *
from .world_info import WorldInfo

from collections import deque
from operator import eq as equals_operator
from time import monotonic

__all__ = ["ConnectionInterface", "ClientInterface", "ServerInterface"]


class ConnectionInterface(NetmodeSwitch, metaclass=InstanceRegister):
    """Interface for remote peer
    Mediates a connection instance between local and remote peer"""

    subclasses = {}

    def on_initialised(self):
        # Maximum sequence number value
        self.sequence_max_size = 255 ** 2
        self.sequence_handler = get_handler(
                                TypeFlag(int, max_value=self.sequence_max_size)
                                )

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
        self.handshake_packer = get_handler(TypeFlag(int))

        # Storage for packets requesting ack or received
        self.requested_ack = {}
        self.received_window = deque()

        # Current indicators of latest out/incoming sequence numbers
        self.local_sequence = 0
        self.remote_sequence = 0

        # Time out for connection before it is deleted
        self.time_out_delay = 4
        self.last_received = monotonic()

        # Simple connected status
        self.status = ConnectionStatus.pending  # @UndefinedVariable

        # Maintains an actual connection
        self.connection = None

        # Estimate available bandwidth
        self.bandwidth = conversion(1, "Mb", "B")
        self.packet_growth = conversion(0.5, "KB", "B")

        # Bandwidth throttling
        self.tagged_throttle_sequence = None
        self.throttle_pending = False

        # Internal packet data
        self.internal_data = []

    def on_unregistered(self):
        """Unregistration callback"""
        if self.connection:
            self.connection.on_delete()

    def on_connected(self):
        self.status = ConnectionStatus.connected  # @UndefinedVariable
        ConnectionSuccessSignal.invoke(target=self)

    def on_failure(self):
        self.status = ConnectionStatus.failed  # @UndefinedVariable

    @classmethod
    def by_status(cls, status, comparator=equals_operator):
        """Filter connections by status

        :param status: status query
        :param comparator: comparison callback for filter"""
        count = 0
        for interface in cls:
            if comparator(interface.status, status):
                count += 1
        return count

    @property
    def next_local_sequence(self):
        """:returns: next local packet sequence identifier"""
        current_sequence = self.local_sequence
        self.local_sequence = (current_sequence + 1) if (current_sequence <
                                             self.sequence_max_size) else 0
        return self.local_sequence

    def sequence_more_recent(self, base, sequence):
        """Compares two sequence identifiers
        determines if one is greater than the other

        :param base: base sequence to compare against
        :param sequence: sequence tested against base"""
        half_seq = (self.sequence_max_size / 2)
        return (((base > sequence) and (base - sequence) <= half_seq)
            or ((sequence > base) and (sequence - base) > half_seq))

    def send(self, network_tick):
        """Pulls data from connection interfaces to send

        :param network_tick: if this is a network tick"""

        # Check for timeout
        if (monotonic() - self.last_received) > self.time_out_delay:
            self.status = ConnectionStatus.timeout  # @UndefinedVariable

            err = ConnectionTimeoutError("Connection timed out")
            ConnectionErrorSignal.invoke(err, target=self)
            return

        # Self-incrementing sequence property
        sequence = self.next_local_sequence

        # If we are waiting to detect when throttling will have returned
        if self.throttle_pending and self.tagged_throttle_sequence is None:
            self.tagged_throttle_sequence = sequence

        # If not connected setup handshake
        if self.status == ConnectionStatus.pending:  # @UndefinedVariable
            packet_collection = PacketCollection(self.send_handshake())
            self.status = ConnectionStatus.handshake

        # If connected send normal data
        elif self.status == ConnectionStatus.connected:  # @UndefinedVariable
            packet_collection = self.connection.send(network_tick,
                                                     self.bandwidth)

        # Don't send any data between states
        else:
            return

        # Include any re-send
        if self.internal_data:
            # Read internal_data
            packet_collection += PacketCollection(self.internal_data)
            # Empty internal_data
            self.internal_data.clear()

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

    def handle_packet(self, packet):
        # Called for handshake protocol
        packet_protocol = packet.protocol

        if packet_protocol > Protocols.request_handshake and self.status != ConnectionStatus.pending:
            self.connection.receive(packet)

        elif packet_protocol == Protocols.request_handshake:
            self.handle_handshake(packet)

        else:
            err = TypeError("Unable to process packet with protocol {}"
                            .format(packet_protocol))
            ConnectionErrorSignal.invoke(err, target=self)
            self.request_unregistration()

    def update_reliable_info(self, ack_base, sliding_window):
        requested_ack = self.requested_ack
        window_size = self.ack_window

        # Iterate over ACK bitfield
        for index in range(window_size):
            sequence_ = ack_base - (index + 1)

            # If it was acked successfully
            flag = sliding_window[index]

            # If we are waiting for this packet, acknowledge it
            if (flag and sequence_ in requested_ack):
                requested_ack.pop(sequence_).on_ack()

                # If a packet has had time to return since throttling began
                if sequence_ == self.tagged_throttle_sequence:
                    self.stop_throttling()

        # Acknowledge the sequence of this packet
        if ack_base in self.requested_ack:
            requested_ack.pop(ack_base).on_ack()

            # If a packet has had time to return since throttling began
            if ack_base == self.tagged_throttle_sequence:
                self.stop_throttling()

        # Dropped locals
        buffer = self.internal_data
        missed_ack = False

        # Find packets we think are dropped and resend them
        considered_dropped = set(seq_ for seq_ in requested_ack if
                                 (ack_base - seq_) >= window_size)
        # If the packet drops off the ack_window assume it is lost
        for sequence_ in considered_dropped:
            # Only reliable members asked to be informed if received/dropped
            reliable_collection = requested_ack.pop(sequence_).to_reliable()
            reliable_collection.on_not_ack()

            missed_ack = True
            buffer.extend(reliable_collection.members)

        # Respond to network conditions
        if missed_ack and not self.throttle_pending:
            self.start_throttling()

    def receive(self, bytes_):
        """Handles received bytes from peer

        :param bytes_: data from peer"""

        # Get the sequence id
        sequence = self.sequence_handler.unpack_from(bytes_)
        bytes_ = bytes_[self.sequence_handler.size():]

        # Get the base value for the bitfield
        ack_base = self.sequence_handler.unpack_from(bytes_)
        bytes_ = bytes_[self.sequence_handler.size():]

        # Read the acknowledgement bitfield
        self.ack_packer.unpack_merge(self.ack_bitfield, bytes_)
        bytes_ = bytes_[self.ack_packer.size(bytes_):]

        # Dictionary of packets waiting for acknowledgement
        self.update_reliable_info(ack_base, self.ack_bitfield)

        # If we receive a newer foreign sequence, update our local record
        if self.sequence_more_recent(sequence, self.remote_sequence):
            self.remote_sequence = sequence

        # Update received window
        self.received_window.append(sequence)
        if len(self.received_window) > self.ack_window:
            self.received_window.popleft()

        # Store the received time
        self.last_received = monotonic()

        # Handle received packets
        PacketCollection.iter_bytes(bytes_, self.handle_packet)


@netmode_switch(Netmodes.server)  # @UndefinedVariable
class ServerInterface(ConnectionInterface):

    def on_initialised(self):
        """Initialised callback"""
        super().on_initialised()

        self._auth_error = None

    def on_unregistered(self):
        if self.connection is not None:
            ConnectionDeletedSignal.invoke(self.connection.replicable)

        super().on_unregistered()

    def on_disconnect(self):
        self.status = ConnectionStatus.disconnected  # @UndefinedVariable

    def handle_packet(self, packet):
        if packet.protocol == Protocols.request_disconnect:
            self.on_disconnect()

        else:
            super().handle_packet(packet)

    def send_handshake(self):
        '''Creates a handshake packet
        Either acknowledges connection or sends error state'''
        connection_failed = self.connection is None

        if connection_failed:
            if self._auth_error:
                # Send the error code
                handshake_type = self.handshake_packer.pack(
                                        HandshakeState.failure)
                err_name = self.error_packer.pack(
                                          type(self._auth_error).type_name)
                err_body = self.error_packer.pack(
                                          self._auth_error.args[0])

                # Yield a reliable packet
                return Packet(protocol=Protocols.request_handshake,
                              payload=handshake_type + err_name + err_body,
                              on_success=ignore_arguments(self.on_failure))

        else:
            # Send acknowledgement
            handshake_type = self.handshake_packer.pack(
                                    HandshakeState.success)
            return Packet(protocol=Protocols.request_handshake,
                          payload=handshake_type + self.netmode_packer.pack(WorldInfo.netmode),
                          on_success=ignore_arguments(self.on_connected))

    def handle_handshake(self, packet):
        """Receives a handshake packet
        Either proceeds to setup connection or stores the error"""

        # Unpack data
        handshake_type = self.handshake_packer.unpack_from(packet.payload)
        payload = packet.payload[self.handshake_packer.size():]
        netmode = self.netmode_packer.unpack_from(payload)

        # Store replicable
        try:
            if self.connection is not None:
                raise NetworkError("Connection already in mediation")
            if handshake_type != HandshakeState.request:
                raise NetworkError("Handshake request was invalid")
            WorldInfo.rules.pre_initialise(self.instance_id, netmode)

        # If a NetworkError is raised store the result
        except NetworkError as err:
            self._auth_error = err

        else:
            self.connection = connection = Connection(netmode)
            returned_replicable = WorldInfo.rules.post_initialise(connection)
            # Replicable is boolean false until registered
            # User can force register though!
            if returned_replicable is not None:
                connection.replicable = returned_replicable


@netmode_switch(Netmodes.client)
class ClientInterface(ConnectionInterface):

    @DisconnectSignal.global_listener
    def disconnect_from_server(self, quit_callback):
        packet = Packet(Protocols.request_disconnect,
                        on_success=ignore_arguments(quit_callback))
        self.internal_data.append(packet)

    def send_handshake(self):
        '''Creates a handshake packet
        Sends netmode to server'''
        handshake_type = self.handshake_packer.pack(HandshakeState.request)
        netmode = self.netmode_packer.pack(WorldInfo.netmode)

        return Packet(protocol=Protocols.request_handshake,
                      payload=handshake_type + netmode,
                      reliable=True)

    def handle_handshake(self, packet):
        """Receives a handshake packet
        Either proceeds to setup connection or invokes the error"""

        # Unpack data
        handshake_type = self.handshake_packer.unpack_from(packet.payload)
        payload = packet.payload[self.handshake_packer.size():]

        if handshake_type == HandshakeState.failure:
            error_body = packet.payload[self.error_packer.size(payload):]
            error_type = self.error_packer.unpack_from(payload)
            error_message = self.error_packer.unpack_from(error_body)
            error_class = NetworkError.from_type_name(error_type)

            raised_error = error_class(error_message)

            ConnectionErrorSignal.invoke(raised_error, target=self)

        # Get remote network mode
        elif handshake_type == HandshakeState.success:
            netmode = self.netmode_packer.unpack_from(payload)

            # If we did not have an error then we succeeded
            self.connection = Connection(netmode)
            self.on_connected()

        else:
            err = NetworkError("Failed to determine handshake protocol")
            ConnectionErrorSignal.invoke(err, target=self)

    def receive(self, bytes_):
        super().receive(bytes_)

        if self.connection:
            self.connection.received_all()
