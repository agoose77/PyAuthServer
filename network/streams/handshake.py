from .streams import ProtocolHandler, response_protocol, send_state, StatusDispatcher, Stream
from .replication import ReplicationStream

from ..decorators import with_tag
from ..errors import NetworkError
from ..enums import ConnectionStates, ConnectionProtocols, Netmodes
from ..handlers import get_handler
from ..packet import Packet
from ..signals import ConnectionErrorSignal, ConnectionSuccessSignal, ConnectionDeletedSignal, ConnectionTimeoutSignal
from ..tagged_delegate import DelegateByNetmode
from ..type_flag import TypeFlag
from ..world_info import WorldInfo

from time import clock

__all__ = 'HandshakeStream', 'ServerHandshakeStream', 'ClientHandshakeStream'


# Handshake Streams
class HandshakeStream(Stream, ProtocolHandler, StatusDispatcher, DelegateByNetmode):
    subclasses = {}

    def __init__(self, dispatcher):
        Stream.__init__(self, dispatcher)
        StatusDispatcher.__init__(self)

        self.state = ConnectionStates.pending

        self.dispatcher = dispatcher

        self.replication_stream = None
        self.connection_info = None
        self.remove_connection = None

        self.timeout_duration = 10
        self._last_received_time = clock()

        # Additional data
        self.netmode_packer = get_handler(TypeFlag(int))
        self.string_packer = get_handler(TypeFlag(str))

    @property
    def timed_out(self):
        """If this stream has not received anything for an interval greater or equal to the timeout duration"""
        return (clock() - self._last_received_time) > self.timeout_duration

    def _cleanup(self):
        if callable(self.remove_connection):
            self.remove_connection()

        if self.replication_stream is not None:
            self.replication_stream.on_disconnected()

    def on_timeout(self):
        self._cleanup()

        self.logger.info("Timed out after {} seconds".format(self.timeout_duration))
        ConnectionTimeoutSignal.invoke(target=self)

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
        self._cleanup()

        ConnectionErrorSignal.invoke(target=self)

    @response_protocol(ConnectionProtocols.request_disconnect)
    def receive_disconnect_request(self, data):
        self._cleanup()

        self.state = ConnectionStates.disconnected

    @response_protocol(ConnectionProtocols.request_handshake)
    def receive_handshake_request(self, data):
        # Only if we're not already connected
        if self.state != ConnectionStates.pending:
            return

        netmode, netmode_size = self.netmode_packer.unpack_from(data)
        connection_info = self.connection_info

        try:
            WorldInfo.rules.pre_initialise(connection_info, netmode)

        except NetworkError as err:
            self.logger.error("Connection was refused: {}".format(err))
            self.handshake_error = err

        self.state = ConnectionStates.handshake

    @send_state(ConnectionStates.handshake)
    def send_handshake_result(self, network_tick, bandwidth):
        connection_failed = self.handshake_error is not None

        if connection_failed:
            pack_string = self.string_packer.pack
            error_type = type(self.handshake_error).type_name
            error_body = self.handshake_error.args[0]
            error_data = pack_string(error_type) + pack_string(error_body)

            # Set failed state
            self.state = ConnectionStates.failed
            ConnectionErrorSignal.invoke(target=self)

            # Send result
            return Packet(protocol=ConnectionProtocols.handshake_failed, payload=error_data,
                          on_success=self.on_ack_handshake_failed)

        else:
            self.replication_stream = self.dispatcher.create_stream(ReplicationStream)
            # Set success state
            self.state = ConnectionStates.connected
            ConnectionSuccessSignal.invoke(target=self)

            # Send result
            return Packet(protocol=ConnectionProtocols.handshake_success, reliable=True)

    @send_state(ConnectionStates.pending)
    def invoke_handshake(self, network_tick, bandwidth):
        """Invoke handshake attempt on client, used for multicasting

        :param network_tick: is a full network tick
        :param bandwidth: available bandwidth
        """
        return Packet(protocol=ConnectionProtocols.invoke_handshake)


@with_tag(Netmodes.client)
class ClientHandshakeStream(HandshakeStream):

    @send_state(ConnectionStates.pending)
    def send_handshake_request(self, network_tick, bandwidth):
        self.state = ConnectionStates.handshake
        netmode_data = self.netmode_packer.pack(WorldInfo.netmode)
        return Packet(protocol=ConnectionProtocols.request_handshake, payload=netmode_data, reliable=True)

    @response_protocol(ConnectionProtocols.handshake_success)
    def receive_handshake_success(self, data):
        if self.state != ConnectionStates.handshake:
            return

        self.state = ConnectionStates.connected
        self.replication_stream = self.dispatcher.create_stream(ReplicationStream)

        ConnectionSuccessSignal.invoke(target=self)

    @response_protocol(ConnectionProtocols.invoke_handshake)
    def receive_multicast_ping(self, data):
        # Just handle packet, it's only to trigger connection
        pass

    @response_protocol(ConnectionProtocols.handshake_failed)
    def receive_handshake_failed(self, data):
        error_type, type_size = self.string_packer.unpack_from(data)
        error_message, message_size = self.string_packer.unpack_from(data, type_size)

        error_class = NetworkError.from_type_name(error_type)
        raised_error = error_class(error_message)

        self.logger.error("Authentication failed: {}".format(raised_error))
        self.state = ConnectionStates.failed

        ConnectionErrorSignal.invoke(raised_error, target=self)
