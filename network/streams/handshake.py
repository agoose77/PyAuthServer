from .streams import ProtocolHandler, response_protocol, send_state, StatusDispatcher
from .replication import ReplicationStream

from ..decorators import with_tag
from ..errors import NetworkError
from ..enums import ConnectionStatus, ConnectionProtocols, Netmodes
from ..handler_interfaces import get_handler
from ..logger import logger
from ..packet import Packet
from ..signals import ConnectionErrorSignal, ConnectionSuccessSignal, ConnectionDeletedSignal, ConnectionTimeoutSignal
from ..tagged_delegate import DelegateByNetmode
from ..type_flag import TypeFlag
from ..world_info import WorldInfo

from time import clock

__all__ = 'HandshakeStream', 'ServerHandshakeStream', 'ClientHandshakeStream'


# Handshake Streams
class HandshakeStream(ProtocolHandler, StatusDispatcher, DelegateByNetmode):
    subclasses = {}

    def __init__(self, dispatcher):
        self.status = ConnectionStatus.pending

        self.time_created = clock()
        self.dispatcher = dispatcher

        self.connection_info = None
        self.remove_connection = None

        self.timeout_duration = 5.0

        # Additional data
        self.netmode_packer = get_handler(TypeFlag(int))
        self.string_packer = get_handler(TypeFlag(str))

    @property
    def timed_out(self):
        return (clock() - self.time_created) > self.timeout_duration and self.status < ConnectionStatus.connected

    def on_timeout(self):
        if callable(self.remove_connection):
            self.remove_connection()

        ConnectionTimeoutSignal.invoke(target=self)

    def pull_packets(self, network_tick, bandwidth):
        if self.timed_out:
            self.on_timeout()

        return super().pull_packets(network_tick, bandwidth)


@with_tag(Netmodes.server)
class ServerHandshakeStream(HandshakeStream):
    """Manages connection state for the server"""

    def __init__(self, dispatcher):
        super().__init__(dispatcher)

        self.handshake_error = None
        self.replication_stream = None

    def on_ack_handshake_failed(self, packet):
        self.status = ConnectionStatus.failed

        ConnectionErrorSignal.invoke(target=self)

        if callable(self.remove_connection):
            self.remove_connection()

    def on_ack_handshake_success(self, packet):
        self.status = ConnectionStatus.connected

        ConnectionSuccessSignal.invoke(target=self)

    @response_protocol(ConnectionProtocols.request_disconnect)
    def receive_disconnect_request(self, data):
        self.status = ConnectionStatus.disconnected

        if self.replication_stream is None:
            return

        ConnectionDeletedSignal.invoke(target=self)
        self.replication_stream.on_disconnected()

        if callable(self.remove_connection):
            self.remove_connection()

    @response_protocol(ConnectionProtocols.request_handshake)
    def receive_handshake_request(self, data):
        # Only if we're not already connected
        if self.status != ConnectionStatus.pending:
            return

        netmode, netmode_size = self.netmode_packer.unpack_from(data)
        connection_info = self.connection_info

        try:
            WorldInfo.rules.pre_initialise(connection_info, netmode)

        except NetworkError as err:
            logger.exception("Connection was refused")
            self.handshake_error = err

        else:
            self.replication_stream = self.dispatcher.create_stream(ReplicationStream)

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
            return Packet(protocol=ConnectionProtocols.handshake_success,
                          on_success=self.on_ack_handshake_success)


@with_tag(Netmodes.client)
class ClientHandshakeStream(HandshakeStream):

    @send_state(ConnectionStatus.pending)
    def send_handshake_request(self, network_tick, bandwidth):
        self.status = ConnectionStatus.handshake

        netmode_data = self.netmode_packer.pack(WorldInfo.netmode)
        return Packet(protocol=ConnectionProtocols.request_handshake, payload=netmode_data)

    @response_protocol(ConnectionProtocols.handshake_success)
    def receive_handshake_success(self, data):
        if self.status != ConnectionStatus.handshake:
            return

        self.status = ConnectionStatus.connected
        self.dispatcher.create_stream(ReplicationStream)

    @response_protocol(ConnectionProtocols.handshake_failed)
    def receive_handshake_failed(self, data):
        error_type, type_size = self.string_packer.unpack_from(data)

        error_message, message_size = self.string_packer.unpack_from(data, type_size)

        error_class = NetworkError.from_type_name(error_type)
        raised_error = error_class(error_message)

        logger.error(raised_error)
        ConnectionErrorSignal.invoke(raised_error, target=self)
        self.status = ConnectionStatus.failed