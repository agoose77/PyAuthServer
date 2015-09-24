from .handlers import get_handler
from .type_flag import TypeFlag

from functools import lru_cache

__all__ = ['PacketCollection', 'Packet']


class PacketCollection:
    """Container for a sequence of Packet instances"""

    __slots__ = "packets"

    def __init__(self, packets=None):
        if packets is None:
            packets = []

        self.packets = packets

    @property
    def reliable_packets(self):
        """The reliable packets of this packet collection"""
        return [m for m in self.packets if m.reliable]

    @property
    def unreliable_packets(self):
        """The unreliable packets of this packet collection"""
        return [m for m in self.packets if not m.reliable]

    @property
    def size(self):
        return len(self.to_bytes())

    def to_reliable(self):
        """Create PacketCollection of reliable packets

        :rtype: :py:class:`network.packet.PacketCollection`
        """
        return self.__class__(self.reliable_packets)

    def to_unreliable(self):
        """Create PacketCollection of unreliable packets

        :rtype: :py:class:`network.packet.PacketCollection`
        """
        return self.__class__(self.unreliable_packets)

    def on_ack(self):
        """Callback for acknowledgement of packet receipt"""
        for member in self.packets:
            member.on_ack()

    def on_not_ack(self):
        """Callback for assumption of a lost packet"""
        for member in self.reliable_packets:
            member.on_not_ack()

    def to_bytes(self):
        """Writes collection contents to bytes""" 
        return b''.join([m.to_bytes() for m in self.packets])

    @classmethod
    def iter_bytes(cls, bytes_string, callback):
        """Iterates over packets within a byte stream

        :param bytes_string: byte stream
        :param callback: callable object to handle created packets"""
        while bytes_string:
            packet = Packet()
            bytes_string = packet.take_from(bytes_string)
            callback(packet)

    @classmethod
    def from_bytes(cls, bytes_string):
        """Creates PacketCollection instance
        Populates with packets in byte stream

        :param bytes_string: bytes stream
        :rtype: :py:class:`network.packet.PacketCollection`
        """
        collection = cls()
        cls.iter_bytes(bytes_string, collection.packets.append)

        return collection

    def __bool__(self):
        return bool(self.packets)

    def __str__(self):
        return '\n'.join(str(m) for m in self.packets)

    def __add__(self, other):
        if isinstance(other, Packet):
            packets = self.packets.copy()
            packets.append(other)
            return self.__class__(packets)

        else:
            return self.__class__(self.packets + other.packets)

    def __radd__(self, other):
        assert isinstance(other, Packet)
        packets = [other]
        packets.extend(self.packets)
        return self.__class__(packets)

    def __iter__(self):
        return iter(self.packets)

    __bytes_string_ = to_bytes


class Packet:
    """Interface class for packets sent over the network.

    Supports protocol and length header
    """
    __slots__ = "protocol", "payload", "reliable", "on_success", "on_failure"

    _protocol_handler = get_handler(TypeFlag(int))
    _size_handler = get_handler(TypeFlag(int, max_value=1000))

    def __init__(self, protocol=None, payload=b'', *, reliable=False, on_success=None, on_failure=None):
        # Force reliability for callbacks
        reliable = reliable or bool(on_success or on_failure)

        self.on_success = on_success
        self.on_failure = on_failure
        self.protocol = protocol
        self.payload = payload
        self.reliable = reliable

    @property
    def size(self):
        """Length of packet when reduced to bytes"""
        return len(self.to_bytes())

    def on_ack(self):
        """Called when packet is acknowledged.

        Invokes on_success callback
        """
        if callable(self.on_success):
            self.on_success(self)

    def on_not_ack(self):
        """Called when packet is considered dropped.

        Invokes on_failure callback if this packet is reliable
        """
        if callable(self.on_failure):
            self.on_failure(self)

    @lru_cache()
    def to_bytes(self):
        """Reduces packet into bytes

        :rtype: bytes
        """
        data = self._protocol_handler.pack(self.protocol) + self.payload
        return self._size_handler.pack(len(data)) + data

    @classmethod
    def from_bytes(cls, bytes_string):
        """Creates packet instance from bytes

        :param bytes_string: bytes stream
        :rtype: :py:class:`network.packet.Packet`
        """
        packet = cls()
        packet.take_from(bytes_string)
        return packet

    def take_from(self, bytes_string):
        """Populates packet instance with data.

        Offsets returned bytes by length of packet

        :param bytes_string: bytes stream
        :rtype: bytes
        """
        length_handler = self._size_handler
        protocol_handler = self._protocol_handler

        # Read packet length (excluding length character size)
        length, length_size = length_handler.unpack_from(bytes_string)
        bytes_string = bytes_string[length_size:]

        # Read packet protocol
        self.protocol, protocol_size = protocol_handler.unpack_from(bytes_string)
        bytes_string = bytes_string[protocol_size:]

        # Determine the slice index of this payload
        end_index = length - protocol_size

        self.payload = bytes_string[:end_index]
        self.reliable = False

        return bytes_string[end_index:]

    def __add__(self, other):
        """Concatenates two Packets

        :param other: Packet instance
        :rtype: :py:class:`network.packet.PacketCollection`
        """
        if isinstance(other, Packet):
            return PacketCollection([self, other])

        else:
            return NotImplemented

    def __str__(self):
        """String representation of Packet"""
        to_console = ["[Packet]"]
        for key in self.__slots__:
            if key.startswith("_"):
                continue
            to_console.append("{}: {}".format(key, getattr(self, key)))

        return '\n'.join(to_console)

    __bytes__ = to_bytes
