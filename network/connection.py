from collections import deque
from time import clock
from socket import gethostbyname

from .bitfield import BitField
from .conversions import conversion
from .type_flag import TypeFlag
from .handlers import get_handler
from .metaclasses import InstanceRegister
from .packet import PacketCollection
from .streams import Dispatcher, InjectorStream, HandshakeStream


__all__ = "Connection",


class Connection(metaclass=InstanceRegister):
    """Interface for remote peer

    Mediates a connection between local and remote peer
    """

    subclasses = {}

    @classmethod
    def create_connection(cls, address, port):
        address = gethostbyname(address)
        ip_info = address, port

        try:
            return cls.get_from_graph(ip_info)

        except LookupError:
            return cls(ip_info)

    def on_initialised(self):
        # Maximum sequence number value
        self.sequence_max_size = 2 ** 16 - 1
        self.sequence_handler = get_handler(TypeFlag(int, max_value=self.sequence_max_size))

        # Number of packets to ack per packet
        self.ack_window = 32

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
        self.last_received = clock()

        # Estimate available bandwidth
        self.bandwidth = conversion(1, "Mb", "B")
        self.packet_growth = conversion(0.5, "KB", "B")

        # Bandwidth throttling
        self.tagged_throttle_sequence = None
        self.throttle_pending = False

        # Internal packet data
        self.dispatcher = Dispatcher()
        self.injector = self.dispatcher.create_stream(InjectorStream)

        self.handshake = self.dispatcher.create_stream(HandshakeStream)
        self.handshake.connection_info = self.instance_id
        self.handshake.remove_connection = self.deregister

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

    def handle_reliable_information(self, ack_base, ack_bitfield):
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
        redelivery_queue = self.injector.queue
        # If the packet drops off the ack_window assume it is lost
        for absolute_sequence in considered_dropped:
            # Only reliable members asked to be informed if received/dropped
            reliable_collection = requested_ack.pop(absolute_sequence).to_reliable()
            reliable_collection.on_not_ack()

            missed_ack = True
            redelivery_queue.extend(reliable_collection.members)

        # Respond to network conditions
        if missed_ack and not self.throttle_pending:
            self.start_throttling()

    def receive(self, bytes_string):
        """Handle received bytes from peer

        :param bytes_string: data from peer
        """
        # Get the sequence id
        sequence, offset = self.sequence_handler.unpack_from(bytes_string)

        # Get the base value for the bitfield
        ack_base, ack_base_size = self.sequence_handler.unpack_from(bytes_string, offset=offset)
        offset += ack_base_size

        # Read the acknowledgement bitfield
        ack_bitfield_size = self.ack_packer.unpack_merge(self.incoming_ack_bitfield, bytes_string, offset=offset)
        offset += ack_bitfield_size

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
        self.last_received = clock()

        # Handle received packets
        packet_collection = PacketCollection.from_bytes(bytes_string[offset:])
        self.dispatcher.handle_packets(packet_collection)

    def send(self, network_tick):
        """Pull data from connection interfaces to send

        :param network_tick: if this is a network tick
        """
        # Increment the local sequence, ensure that the sequence does not overflow, by wrapping it around
        sequence = self.local_sequence = (self.local_sequence + 1) % (self.sequence_max_size + 1)
        remote_sequence = self.remote_sequence

        # If we are waiting to detect when throttling will have returned
        if self.throttle_pending and self.tagged_throttle_sequence is None:
            self.tagged_throttle_sequence = sequence

        packet_collection = self.dispatcher.pull_packets(network_tick, self.bandwidth)

        # Get ack bitfield for reliable feedback
        ack_bitfield = self.get_reliable_information(remote_sequence)

        # Store acknowledge request for reliable members of packet
        self.requested_ack[sequence] = packet_collection

        # Construct header information
        payload = [self.sequence_handler.pack(sequence), self.sequence_handler.pack(remote_sequence),
                   self.ack_packer.pack(ack_bitfield)]

        # Include user defined payload
        packet_bytes = packet_collection.to_bytes()
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
