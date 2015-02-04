from .streams import ProtocolHandler, response_protocol, send_state, StatusDispatcher
from .replication import ReplicationStream

from ..decorators import with_tag
from ..errors import NetworkError
from ..enums import ConnectionState, ConnectionProtocols, Netmodes
from ..handlers import get_handler
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
        self.state = ConnectionState.pending

        self.dispatcher = dispatcher

        self.connection_info = None
        self.remove_connection = None

        self.timeout_duration = 3000.0
        self._last_received_time = clock()

        # Additional data
        self.netmode_packer = get_handler(TypeFlag(int))
        self.string_packer = get_handler(TypeFlag(str))

    @property
    def timed_out(self):
        return (clock() - self._last_received_time) > self.timeout_duration

    def on_timeout(self):
        if callable(self.remove_connection):
            self.remove_connection()

        ConnectionTimeoutSignal.invoke(target=self)
        self.replication_stream.on_disconnected()

    def handle_packets(self, packet_collection):
        super().handle_packets(packet_collection)

        self._last_received_time = clock()

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
        if callable(self.remove_connection):
            self.remove_connection()

        ConnectionErrorSignal.invoke(target=self)

    @response_protocol(ConnectionProtocols.request_disconnect)
    def receive_disconnect_request(self, data):
        self.state = ConnectionState.disconnected

        if self.replication_stream is None:
            return

        ConnectionDeletedSignal.invoke(target=self)
        self.replication_stream.on_disconnected()

        if callable(self.remove_connection):
            self.remove_connection()

    @response_protocol(ConnectionProtocols.request_handshake)
    def receive_handshake_request(self, data):
        # Only if we're not already connected
        if self.state != ConnectionState.pending:
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
            self.state = ConnectionState.handshake

    @send_state(ConnectionState.handshake)
    def send_handshake_result(self, network_tick, bandwidth):
        connection_failed = self.handshake_error is not None

        if connection_failed:
            pack_string = self.string_packer.pack
            error_type = type(self._auth_error).type_name
            error_body = self._auth_error.args[0]
            error_data = pack_string(error_type + error_body)

            # Set failed state
            self.state = ConnectionState.failed
            ConnectionErrorSignal.invoke(target=self)

            # Send result
            return Packet(protocol=ConnectionProtocols.handshake_failed, payload=error_data,
                          on_success=self.on_ack_handshake_failed)

        else:
            # Set success state
            self.state = ConnectionState.connected
            ConnectionSuccessSignal.invoke(target=self)

            # Send result
            return Packet(protocol=ConnectionProtocols.handshake_success)

    @send_state(ConnectionState.pending)
    def invoke_handshake(self, network_tick, bandwidth):
        """Invoke handshake attempt on client, used for multicasting

        :param network_tick: is a full network tick
        :param bandwidth: available bandwidth
        """
        return Packet(protocol=ConnectionProtocols.invoke_handshake)


@with_tag(Netmodes.client)
class ClientHandshakeStream(HandshakeStream):

    @send_state(ConnectionState.pending)
    def send_handshake_request(self, network_tick, bandwidth):
        self.state = ConnectionState.handshake

        netmode_data = self.netmode_packer.pack(WorldInfo.netmode)
        return Packet(protocol=ConnectionProtocols.request_handshake, payload=netmode_data)

    @response_protocol(ConnectionProtocols.handshake_success)
    def receive_handshake_success(self, data):
        if self.state != ConnectionState.handshake:
            return

        self.state = ConnectionState.connected
        self.dispatcher.create_stream(ReplicationStream)

        ConnectionSuccessSignal.invoke(target=self)

    @response_protocol(ConnectionProtocols.invoke_handshake)
    def receive_multicast_ping(self, data):
        # Can't connect to new servers when involved with another
        if self.state != ConnectionState.pending:
            return

        self.state = ConnectionState.pending

    @response_protocol(ConnectionProtocols.handshake_failed)
    def receive_handshake_failed(self, data):
        error_type, type_size = self.string_packer.unpack_from(data)

        error_message, message_size = self.string_packer.unpack_from(data, type_size)

        error_class = NetworkError.from_type_name(error_type)
        raised_error = error_class(error_message)

        logger.error(raised_error)
        self.state = ConnectionState.failed

        ConnectionErrorSignal.invoke(raised_error, target=self)