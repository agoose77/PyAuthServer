from collections import deque
from logging import getLogger, Formatter, StreamHandler
from time import strftime, clock

from .bitfield import BitField
from .messages import MessagePasser
from .enums import PacketProtocols
from .handlers import get_handler, TypeFlag
from .packet import PacketCollection, Packet
from .factory import ProtectedInstance


__all__ = "Connection",


class ConnectionLoggerFormatter(Formatter):

    def formatTime(self, record, datefmt):
        return strftime("%H:%M:%S")


class Connection(ProtectedInstance):
    """Interface for remote peer.

    Mediates a connection between local and remote peer.
    """

    create_default_context = False

    def __init__(self, connection_info, network_manager):
        self.connection_info = connection_info
        self.network_manager = network_manager

        # Maximum sequence number value
        self.sequence_max_size = 2 ** 16 - 1
        self.sequence_handler = get_handler(TypeFlag(int, max_value=self.sequence_max_size))

        # Number of packets to ack per packet
        self.ack_window = 32

        # BitField and bitfield size
        self.incoming_ack_bitfield = BitField(self.ack_window)
        self.outgoing_ack_bitfield = BitField(self.ack_window)
        self.ack_packer = get_handler(TypeFlag(BitField, fields=self.ack_window))

        # Storage for packets requesting ack or received
        self.requested_ack = {}
        self.received_window = deque(maxlen=self.ack_window)

        # Current indicators of latest out/incoming sequence numbers
        self.local_sequence = 0
        self.remote_sequence = 0

        # Estimate available bandwidth
        self.bandwidth = 1000
        self.packet_growth = 500

        # Bandwidth throttling
        self.tagged_throttle_sequence = None
        self.throttle_pending = False

        # Support logging
        self.logger = self._create_logger()

        self.last_received_time = None
        self.send_heartbeat_when_idle = True

        self._queue = []

        self.pre_receive_callbacks = []
        self.post_receive_callbacks = []
        self.pre_send_callbacks = []

        self.messenger = MessagePasser()
        # Ignore heartbeat packet
        self.messenger.add_subscriber(PacketProtocols.heartbeat, lambda packet: None)

    def _is_more_recent(self, base, sequence):
        """Compare two sequence identifiers and determine if one is newer than the other

        :param base: base sequence to compare against
        :param sequence: sequence tested against base
        """
        half_seq = (self.sequence_max_size / 2)
        return ((base > sequence) and (base - sequence) <= half_seq) or \
               ((sequence > base) and (sequence - base) > half_seq)

    def _create_logger(self):
        logger = getLogger(repr(self))
        handler = StreamHandler()

        formatter = ConnectionLoggerFormatter('%(levelname)s - [%(asctime)s - %(name)s] {%(message)s\}')
        handler.setFormatter(formatter)

        logger.addHandler(handler)
        return logger

    def _get_reliable_information(self, remote_sequence):
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

    def _update_reliable_information(self, ack_base, ack_bitfield):
        """Update internal packet management, concerning dropped packets and available bandwidth

        :param ack_base: base sequence for ack window
        :param ack_bitfield: ack window bitfield
        """
        requested_ack = self.requested_ack
        window_size = self.ack_window

        # Iterate over ACK bitfield
        for relative_sequence in range(window_size):
            absolute_sequence = ack_base - (relative_sequence + 1)

            # If we are waiting for this packet, acknowledge it
            if ack_bitfield[relative_sequence] and absolute_sequence in requested_ack:
                sent_packet = requested_ack.pop(absolute_sequence)
                sent_packet.on_ack()

                # If a packet has had time to return since throttling began
                if absolute_sequence == self.tagged_throttle_sequence:
                    self.stop_throttling()

        # Acknowledge the sequence of this packet
        if ack_base in self.requested_ack:
            sent_packet = requested_ack.pop(ack_base)
            sent_packet.on_ack()

            # If a packet has had time to return since throttling began
            if ack_base == self.tagged_throttle_sequence:
                self.stop_throttling()

        # Dropped locals
        missed_ack = False

        # Find packets we think are dropped and resend them
        considered_dropped = [s for s in requested_ack if (ack_base - s) >= window_size]

        queue_packet = self.queue_packet
        # If the packet drops off the ack_window assume it is lost
        for absolute_sequence in considered_dropped:
            # Only reliable members asked to be informed if received/dropped
            reliable_packet = requested_ack.pop(absolute_sequence).to_reliable()
            reliable_packet.on_not_ack()

            missed_ack = True
            queue_packet(reliable_packet)

        # Respond to network conditions
        if missed_ack and not self.throttle_pending:
            self.start_throttling()

    def queue_packet(self, packet):
        # Increment the local sequence, ensure that the sequence does not overflow, by wrapping it around
        sequence = self.local_sequence = (self.local_sequence + 1) % (self.sequence_max_size + 1)
        remote_sequence = self.remote_sequence

        # If we are waiting to detect when throttling will have returned
        if self.throttle_pending and self.tagged_throttle_sequence is None:
            self.tagged_throttle_sequence = sequence

        # Get ack bitfield for reliable feedback
        ack_bitfield = self._get_reliable_information(remote_sequence)

        # Store acknowledge request for reliable members of packet
        self.requested_ack[sequence] = packet

        # Construct header information
        message_parts = [self.sequence_handler.pack(sequence), self.sequence_handler.pack(remote_sequence),
                         self.ack_packer.pack(ack_bitfield), packet.to_bytes()]

        # Force bandwidth to grow (until throttled)
        self.bandwidth += self.packet_growth

        message = b''.join(message_parts)
        self._queue.append(message)

    def receive_message(self, bytes_string):
        """Handle received bytes from peer

        :param bytes_string: data from peer
        """
        # Before receiving
        for callback in self.pre_receive_callbacks:
            callback()

        # Get the sequence id
        sequence, offset = self.sequence_handler.unpack_from(bytes_string)

        # Get the base value for the bitfield
        ack_base, ack_base_size = self.sequence_handler.unpack_from(bytes_string, offset=offset)
        offset += ack_base_size

        # Read the acknowledgement bitfield
        ack_bitfield_size = self.ack_packer.unpack_merge(self.incoming_ack_bitfield, bytes_string, offset=offset)
        offset += ack_bitfield_size

        # TODO allow packet.reject() to un-ack acked packet before check the ack

        # Dictionary of packets waiting for acknowledgement
        self._update_reliable_information(ack_base, self.incoming_ack_bitfield)

        # If we receive a newer foreign sequence, update our local record
        if self._is_more_recent(sequence, self.remote_sequence):
            self.remote_sequence = sequence

        # Update received window
        self.received_window.append(sequence)
        if len(self.received_window) > self.ack_window:
            self.received_window.popleft()

        # Handle received packets, allow possible multiple packets
        packet_collection = PacketCollection.from_bytes(bytes_string[offset:])

        dispatch = self.messenger.send
        for packet in packet_collection.packets:
            dispatch(packet.protocol, packet)

        self.last_received_time = clock()

        # After receiving
        for callback in self.post_receive_callbacks:
            callback()

    def request_messages(self, is_network_tick):
        """Pull data from connection interfaces to send

        :param network_tick: if this is a network tick
        """
        for callback in self.pre_send_callbacks:
            callback(is_network_tick)

        # Use heartbeat packet
        if not self._queue and self.send_heartbeat_when_idle:
            heartbeat_packet = Packet(PacketProtocols.heartbeat)
            self.queue_packet(heartbeat_packet)

        messages = self._queue[:]
        self._queue.clear()

        return messages

    def start_throttling(self):
        """Start updating metric for bandwidth"""
        self.bandwidth /= 2
        self.throttle_pending = True

    def stop_throttling(self):
        """Stop updating metric for bandwidth"""
        self.tagged_throttle_sequence = None
        self.throttle_pending = False
