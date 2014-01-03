from .handler_interfaces import get_handler
from .descriptors import TypeFlag

from functools import lru_cache
from itertools import chain


class PacketCollection:
    __slots__ = "members"

    def __init__(self, members=None):
        if members is None:
            members = []

        # If members support member interface
        if hasattr(members, "members"):
            self.members = members.members

        # Otherwise recreate members
        else:
            self.members = [m for p in members for m in p.members]

    @property
    def reliable_members(self):
        '''The "reliable" members of this packet collection'''
        return (m for m in self.members if m.reliable)

    @property
    def unreliable_members(self):
        '''The "unreliable" members of this packet collection'''
        return (m for m in self.members if not m.reliable)

    @property
    def size(self):
        return len(self.to_bytes())

    def to_reliable(self):
        '''Returns a PacketCollection instance,
        comprised of only reliable members'''
        return self.__class__(self.reliable_members)

    def to_unreliable(self):
        '''Returns a PacketCollection instance,
        comprised of only unreliable members'''
        return self.__class__(self.unreliable_members)

    def on_ack(self):
        '''Callback for acknowledgement of packet receipt'''
        for member in self.members:
            member.on_ack()

    def on_not_ack(self):
        '''Callback for assumption of packet loss'''
        for member in self.reliable_members:
            member.on_not_ack()

    def to_bytes(self):
        return b''.join(m.to_bytes() for m in self.members)

    def from_bytes(self, bytes_):
        members = self.members = []
        append = members.append

        while bytes_:
            packet = Packet()
            bytes_ = packet.take_from(bytes_)
            append(packet)

        return self

    def __bool__(self):
        return bool(self.members)

    def __str__(self):
        return '\n'.join(str(m) for m in self.members)

    def __add__(self, other):
        return self.__class__(self.members + other.members)

    __radd__ = __add__
    __bytes__ = to_bytes


class Packet:
    __slots__ = "protocol", "payload", "reliable", "on_success", "on_failure"

    protocol_handler = get_handler(TypeFlag(int))
    size_handler = get_handler(TypeFlag(int, max_value=1000))

    def __init__(self, protocol=None, payload=None, *, reliable=False,
                 on_success=None, on_failure=None):

        # Force reliability for callbacks
        reliable = reliable or bool(on_success or on_failure)

        self.on_success = on_success
        self.on_failure = on_failure
        self.protocol = protocol
        self.payload = payload
        self.reliable = reliable

    @property
    def members(self):
        '''Returns self as a member of a list'''
        return [self]

    @property
    def size(self):
        return len(self.to_bytes())

    def on_ack(self):
        '''Called when packet is acknowledged'''
        if self.reliable and callable(self.on_success):
            self.on_success(self)

    def on_not_ack(self):
        '''Called when packet is dropped'''
        if callable(self.on_failure):
            self.on_failure(self)

    @lru_cache()
    def to_bytes(self):
        '''Converts packet into bytes'''
        data = self.protocol_handler.pack(self.protocol) + self.payload
        return self.size_handler.pack(len(data)) + data

    def from_bytes(self, bytes_):
        '''Returns packet instance after population
        Takes data from bytes, returns Packet()'''
        self.take_from(bytes_)
        return self

    def take_from(self, bytes_):
        '''Populates packet instance with data
        Returns new slice of bytes string'''
        length_handler = self.size_handler
        protocol_handler = self.protocol_handler

        length = length_handler.unpack_from(bytes_)
        shift = length_handler.size()

        self.protocol = protocol_handler.unpack_from(bytes_[shift:])
        proto_shift = protocol_handler.size()

        self.payload = bytes_[shift + proto_shift:shift + length]
        self.reliable = False

        return bytes_[shift + length:]

    def __add__(self, other):
        return PacketCollection(members=self.members + other.members)

    def __str__(self):
        '''Printable version of a packet'''
        to_console = ["[Packet]"]
        for key in self.__slots__:
            if key.startswith("_"):
                continue
            to_console.append("{}: {}".format(key, getattr(self, key)))

        return '\n'.join(to_console)

    __radd__ = __add__
    __bytes__ = to_bytes
