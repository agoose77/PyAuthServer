from .channel import Channel
from .conditions import is_annotatable
from .decorators import with_tag, get_annotation, set_annotation
from .type_flag import TypeFlag
from .errors import NetworkError
from .connection_stream import ConnectionStream
from .enums import ConnectionProtocols, Netmodes
from .handler_interfaces import get_handler
from .logger import logger
from .tagged_delegate import DelegateByNetmode
from .packet import Packet
from .enums import ConnectionStatus
from .signals import *
from .world_info import WorldInfo

from inspect import getmembers

__all__ = ['Connection', 'ServerConnection', 'ClientConnection']

response_protocol = set_annotation("response_to")
send_state = set_annotation("send_for")


class Connection(DelegateByNetmode):
    """Connection between local host and remote peer
    Represents a successful connection
    """

    def __init__(self):
        self.status = ConnectionStatus.pending

    @classmethod
    def register_subtype(cls):
        cls.senders = senders = {}
        cls.receivers = receivers = {}

        send_getter = get_annotation("send_for")
        receive_getter = get_annotation("response_to")

        for name, value in getmembers(cls, is_annotatable):
            sender_type = send_getter(value)
            if sender_type is not None:
                senders[sender_type] = value

            receiver_type = receive_getter(value)
            if receiver_type is not None:
                receivers[receiver_type] = value

    def send(self, network_tick, bandwidth):
        sender = self.__class__.senders[self.status]
        return sender(self, network_tick, bandwidth)

    def receive(self, packet):
        handler = self.__class__.receivers[packet.protocol]
        handler(self, packet.payload)


class StreamConnection(Connection):
    subclasses = {}

    def __init__(self):
        # Additional data
        self.netmode_packer = get_handler(TypeFlag(int))
        self.string_packer = get_handler(TypeFlag(str))
        self.stream = None

    @send_state(ConnectionStatus.connected)
    def send_stream_data(self, network_tick, bandwidth):
        self.stream.send(network_tick, bandwidth)

    @response_protocol(ConnectionProtocols.connected)
    def receive_stream_data(self, data):
        self.stream.receive(data)


@with_tag(Netmodes.server)
class ServerConnection(StreamConnection):

    def __init__(self):
        # Additional data
        self.netmode_packer = get_handler(TypeFlag(int))
        self.string_packer = get_handler(TypeFlag(str))

        self.handshake_error = None
        self.stream = None

    def on_ack_handshake_failed(self, packet):
        self.status = ConnectionStatus.failed

    def on_ack_handshake_success(self, packet):
        self.status = ConnectionStatus.connected

    @response_protocol(ConnectionProtocols.request_disconnect)
    def receive_disconnect_request(self, data):
        self.status = ConnectionStatus.disconnected

    @response_protocol(ConnectionProtocols.request_handshake)
    def receive_handshake_request(self, data):
        netmode, netmode_size = self.netmode_packer.unpack_from(data)
        connection_info = self.connection_info

        try:
            WorldInfo.rules.pre_initialise(connection_info, netmode)

        except NetworkError as err:
            logger.exception("Connection was refused")
            self.handshake_error = err

        else:
            self.stream = ConnectionStream()

    @send_state(ConnectionStatus.pending)
    def send_handshake_result(self, network_tick, bandwidth):
        connection_failed = self.handshake_error is not None
        self.status = ConnectionStatus.handshake

        if connection_failed:
            pack_string = self.string_packer.pack
            error_type = type(self._auth_error).type_name
            error_body = self._auth_error.args[0]
            error_data = pack_string(error_type + error_body)
            return Packet(protocol=ConnectionProtocols.handshake_failed, payload=error_data,
                          on_success=self.on_ack_handshake_failed)

        else:
            return Packet(protocol=ConnectionProtocols.handshake_succeeded, on_success=self.on_ack_handshake_success)


@with_tag(Netmodes.client)
class ClientConnection(StreamConnection):

    @send_state(ConnectionStatus.pending)
    def send_handshake_request(self, network_tick, bandwidth):
        self.status = ConnectionStatus.handshake

        netmode_data = self.netmode_packer.pack(WorldInfo.netmode)
        return Packet(protocol=ConnectionProtocols.handshake_request, payload=netmode_data)

    @response_protocol(ConnectionProtocols.handshake_success)
    def receive_handshake_success(self, data):
        self.stream = ConnectionStream()
        self.status = ConnectionStatus.connected

    @response_protocol(ConnectionProtocols.handshake_failed)
    def receive_handshake_failed(self, data):
        error_type, type_size = self.string_packer.unpack_from(data)

        error_message, message_size = self.string_packer.unpack_from(data, type_size)

        error_class = NetworkError.from_type_name(error_type)
        raised_error = error_class(error_message)

        logger.error(raised_error)
        ConnectionErrorSignal.invoke(raised_error, target=self)
        self.status = ConnectionStatus.failed