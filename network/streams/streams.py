from inspect import getmembers

from ..conditions import is_annotatable
from ..decorators import get_annotation, set_annotation
from ..metaclasses.register import TypeRegister
from ..packet import PacketCollection


__all__ = 'Dispatcher', 'InjectorStream', 'ProtocolHandler', 'StatusDispatcher', 'response_protocol', 'send_state'

response_protocol = set_annotation("response_to")
send_state = set_annotation("send_for")


class Dispatcher:
    """Dispatches packets to subscriber streams, and requests new packets from them"""

    def __init__(self):
        self.streams = []

    def create_stream(self, stream_cls):
        stream = stream_cls(self)
        self.streams.append(stream)
        return stream

    def handle_packets(self, packet_collection):
        for stream in self.streams:
            stream.handle_packets(packet_collection)

    def pull_packets(self, network_tick, bandwidth):
        packet_collection = PacketCollection()

        for stream in self.streams:
            packets = stream.pull_packets(network_tick, bandwidth)
            if packets is None:
                continue

            packet_collection += packets

        return packet_collection


class InjectorStream:
    """Interface to inject packets into the packet stream"""

    def __init__(self, dispatcher):
        self.queue = []

    @staticmethod
    def handle_packets(packet_collection):
        """Non functional packet handling method

        :param packet: Packet instance
        """
        return

    def pull_packets(self, network_tick, bandwidth):
        if not self.queue:
            return

        packets = PacketCollection(self.queue)
        self.queue.clear()

        return packets


class ProtocolHandler(metaclass=TypeRegister):
    """Dispatches packets to appropriate handlers"""

    @classmethod
    def register_subtype(cls):
        super().register_subtype()

        cls.receivers = receivers = {}

        receive_getter = get_annotation("response_to")
        for name, value in getmembers(cls, is_annotatable):

            receiver_type = receive_getter(value)
            if receiver_type is not None:
                receivers[receiver_type] = value

    def handle_packets(self, packet_collection):
        """Lookup the appropriate handler for given packet type

        :param packet: Packet instance
        """
        receivers = self.__class__.receivers

        for packet in packet_collection:
            try:
                handler = receivers[packet.protocol]

            except KeyError:
                continue

            handler(self, packet.payload)


class StatusDispatcher(metaclass=TypeRegister):
    """Dispatches packets according to current state"""

    def __init__(self):
        self.status = None

    @classmethod
    def register_subtype(cls):
        super().register_subtype()

        cls.senders = senders = {}

        send_getter = get_annotation("send_for")
        for name, value in getmembers(cls, is_annotatable):
            sender_type = send_getter(value)

            if sender_type is not None:
                senders[sender_type] = value

    def pull_packets(self, network_tick, bandwidth):
        try:
            sender = self.__class__.senders[self.status]

        except KeyError:
            return None

        return sender(self, network_tick, bandwidth)
