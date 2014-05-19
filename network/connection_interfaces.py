from .bitfield import BitField
from .connection import Connection
from .conversions import conversion
from .decorators import netmode_switch, ignore_arguments
from .descriptors import TypeFlag
from .enums import ConnectionStatus, Netmodes, Protocols, HandshakeState
from .errors import NetworkError, ConnectionTimeoutError
from .handler_interfaces import get_handler
from .instance_register import InstanceRegister
from .logger import logger
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

    Mediates a connection instance between local and remote peer
    """

    subclasses = {}

    def on_initialised(self):
        # Maximum sequence number value
        self.sequence_max_size = 2 ** 16
        self.sequence_handler = get_handler(TypeFlag(int, max_value=self.sequence_max_size))

        # Number of packets to ack per packet
        self.ack_window = conversion(8, "B", "b")

        # BitField and bitfield size
        self.incoming_ack_bitfield = BitField(self.ack_window)
        self.outgoing_ack_bitfield = BitField(self.ack_window)
        self.ack_packer = get_handler(TypeFlag(BitField, fields=self.ack_window))

        # Additional data
        self.netmode_packer = get_handler(TypeFlag(int))
        self.error_packer = get_handler(TypeFlag(str))

        # Protocol unpacker
        self.protocol_handler = get_handler(TypeFlag(int))
        self.handshake_packer = get_handler(TypeFlag(int))

        # Storage for packets requesting ack or received
        self.requested_ack = {}
        self.received_window = deque(maxlen=self.ack_window)

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

        # Estimate RTT
        self.latency = 0.0
        self.latency_smoothing = 0.1

        # Internal packet data
        self.internal_data = []

    @classmethod
    def by_status(cls, status, comparator=equals_operator):
        """Count number of connections with requested status

        :param status: status query
        :param comparator: comparison callback to test each connection status
        """
        count = 0
        for interface in cls:
            if comparator(interface.status, status):
                count += 1
        return count

    def get_reliable_information(self, remote_sequence):
        """Update stored information for remote peer reliability feedback

        :param remote_sequence: latest received packet's sequence
        """
        # The last received sequence number and received list
        received_window = self.received_window
        ack_bitfield = self.outgoing_ack_bitfield

        # Acknowledge all packets we've received
        for index in range(self.ack_window):
            packet_sqn = remote_sequence - (index + 1)

            if packet_sqn < 0:
                continue

            ack_bitfield[index] = packet_sqn in received_window

        return ack_bitfield

    def handle_packet(self, packet):
        """Handle different packets based upon their protocol

        :param packet: packet in need of handling
        """
        # Called for handshake protocol
        packet_protocol = packet.protocol

        if packet_protocol > Protocols.request_handshake and self.status != ConnectionStatus.pending:
            self.connection.receive(packet)

        elif packet_protocol == Protocols.request_handshake:
            self.handle_handshake(packet)

        else:
            handling_error = TypeError("Unable to process packet with protocol {}".format(packet_protocol))
            logger.error(handling_error)

            ConnectionErrorSignal.invoke(handling_error, target=self)
            self.request_unregistration()

    def handle_reliable_information(self, ack_base, ack_bitfield):
        """Update internal packet management, concerning dropped packets and available bandwidth

        :param ack_base: base sequence for ack window
        :param ack_bitfield: ack window bitfield
        """
        requested_ack = self.requested_ack
        window_size = self.ack_window
        current_time = monotonic()

        # Iterate over ACK bitfield
        for index in range(window_size):
            sequence_ = ack_base - (index + 1)

            # If it was acked successfully
            flag = ack_bitfield[index]

            # If we are waiting for this packet, acknowledge it
            if flag and sequence_ in requested_ack:
                sent_packet = requested_ack.pop(sequence_)
                sent_packet.on_ack()

                self.update_latency_estimate(sent_packet.timestamp - current_time)

                # If a packet has had time to return since throttling began
                if sequence_ == self.tagged_throttle_sequence:
                    self.stop_throttling()

        # Acknowledge the sequence of this packet
        if ack_base in self.requested_ack:
            sent_packet = requested_ack.pop(ack_base)
            sent_packet.on_ack()

            self.update_latency_estimate(sent_packet.timestamp - current_time)

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

    def on_connected(self):
        """Connected callback"""
        self.status = ConnectionStatus.connected  # @UndefinedVariable
        logger.info("Successfully connected to server")

        ConnectionSuccessSignal.invoke(target=self)

    def on_failure(self):
        """Connection Failed callback"""
        self.status = ConnectionStatus.failed  # @UndefinedVariable
        logger.error("Failed to connect to server")

    def on_unregistered(self):
        """Unregistered callback"""
        if self.connection:
            self.connection.on_delete()

    def receive(self, bytes_string):
        """Handle received bytes from peer

        :param bytes_string: data from peer
        """

        # Get the sequence id
        sequence = self.sequence_handler.unpack_from(bytes_string)
        bytes_string = bytes_string[self.sequence_handler.size():]

        # Get the base value for the bitfield
        ack_base = self.sequence_handler.unpack_from(bytes_string)
        bytes_string = bytes_string[self.sequence_handler.size():]

        # Read the acknowledgement bitfield
        self.ack_packer.unpack_merge(self.incoming_ack_bitfield, bytes_string)
        bytes_string = bytes_string[self.ack_packer.size(bytes_string):]

        # Dictionary of packets waiting for acknowledgement
        self.handle_reliable_information(ack_base, self.incoming_ack_bitfield)

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
        PacketCollection.iter_bytes(bytes_string, self.handle_packet)

    def send(self, network_tick):
        """Pull data from connection interfaces to send

        :param network_tick: if this is a network tick
        """

        # Check for timeout
        if (monotonic() - self.last_received) > self.time_out_delay:
            self.status = ConnectionStatus.timeout  # @UndefinedVariable

            err = ConnectionTimeoutError("Connection timed out")
            ConnectionErrorSignal.invoke(err, target=self)
            return

        # Increment the local sequence, ensure that the sequence does not overflow, by wrapping it around
        sequence = self.local_sequence = (self.local_sequence + 1) % (self.sequence_max_size + 1)
        remote_sequence = self.remote_sequence

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

        # Include data from the reliability system
        if self.internal_data:
            # Read internal_data
            packet_collection += PacketCollection(self.internal_data)
            # Empty internal_data
            self.internal_data.clear()

        # Get ack bitfield for reliable feedback
        ack_bitfield = self.get_reliable_information(remote_sequence)

        # Store acknowledge request for reliable members of packet
        packet_collection.timestamp = monotonic()
        self.requested_ack[sequence] = packet_collection

        # Construct header information
        payload = [self.sequence_handler.pack(sequence), self.sequence_handler.pack(remote_sequence),
                   self.ack_packer.pack(ack_bitfield)]

        # Include user defined payload
        packet_bytes = packet_collection.to_bytes()
        if packet_bytes:
            payload.append(packet_bytes)

        # Force bandwidth to grow (until throttled)
        self.bandwidth += self.packet_growth

        return b''.join(payload)

    def sequence_more_recent(self, base, sequence):
        """Compare two sequence identifiers and determine if one is newer than the other

        :param base: base sequence to compare against
        :param sequence: sequence tested against base
        """
        half_seq = (self.sequence_max_size / 2)
        return ((base > sequence) and (base - sequence) <= half_seq) or \
               ((sequence > base) and (sequence - base) > half_seq)

    def start_throttling(self):
        """Start updating metric for bandwidth"""
        self.bandwidth /= 2
        self.throttle_pending = True

    def stop_throttling(self):
        """Stop updating metric for bandwidth"""
        self.tagged_throttle_sequence = None
        self.throttle_pending = False

    def update_latency_estimate(self, new_latency):
        """Smoothly update the internal latency value with a new determined value

        :param new_latency: new latency value
        """
        smooth_factor = self.latency_smoothing
        self.latency = (smooth_factor * self.latency) + (1 - smooth_factor) * new_latency


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
        """Creates a handshake packet, either acknowledges connection or sends error state"""
        connection_failed = self.connection is None

        if connection_failed:

            if self._auth_error:
                # Send the error code
                handshake_type = self.handshake_packer.pack(HandshakeState.failure)
                error_name = type(self._auth_error).type_name
                packed_error_name = self.error_packer.pack(error_name)
                packed_error_body = self.error_packer.pack(self._auth_error.args[0])
                packed_error = packed_error_name + packed_error_body

                # Yield a reliable packet
                return Packet(protocol=Protocols.request_handshake, payload=handshake_type + packed_error,
                              on_success=ignore_arguments(self.on_failure))

            logger.error("Warning: Connection failed for undocumented reason")

        else:
            # Send acknowledgement
            handshake_type = self.handshake_packer.pack(HandshakeState.success)
            packed_netmode = self.netmode_packer.pack(WorldInfo.netmode)

            return Packet(protocol=Protocols.request_handshake, payload=handshake_type + packed_netmode,
                          on_success=ignore_arguments(self.on_connected))

    def handle_handshake(self, packet):
        """Receives a handshake packet, either proceeds to setup connection or stores the error"""

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
            logger.exception()
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
        packet = Packet(Protocols.request_disconnect, on_success=ignore_arguments(quit_callback))
        self.internal_data.append(packet)

    def send_handshake(self):
        """Creates a handshake packet, sends netmode to server"""
        handshake_type = self.handshake_packer.pack(HandshakeState.request)
        netmode = self.netmode_packer.pack(WorldInfo.netmode)

        return Packet(protocol=Protocols.request_handshake, payload=handshake_type + netmode, reliable=True)

    def handle_handshake(self, packet):
        """Receives a handshake packet, rither proceeds to setup connection or invokes the error"""

        # Unpack data
        handshake_type = self.handshake_packer.unpack_from(packet.payload)
        payload = packet.payload[self.handshake_packer.size():]

        if handshake_type == HandshakeState.failure:
            error_body = packet.payload[self.error_packer.size(payload):]
            error_type = self.error_packer.unpack_from(payload)
            error_message = self.error_packer.unpack_from(error_body)
            error_class = NetworkError.from_type_name(error_type)

            raised_error = error_class(error_message)

            logger.error(raised_error)
            ConnectionErrorSignal.invoke(raised_error, target=self)

        # Get remote network mode
        elif handshake_type == HandshakeState.success:
            netmode = self.netmode_packer.unpack_from(payload)

            # If we did not have an error then we succeeded
            self.connection = Connection(netmode)
            self.on_connected()

        else:
            unknown_error = NetworkError("Failed to determine handshake protocol")

            logger.error(unknown_error)
            ConnectionErrorSignal.invoke(unknown_error, target=self)

    def receive(self, bytes_string):
        super().receive(bytes_string)

        if self.connection:
            self.connection.received_all()
