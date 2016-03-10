from time import clock

from .helpers import register_protocol_listeners, get_state_senders, on_protocol
from .replication import ClientReplicationManager, ServerReplicationManager
from ..errors import NetworkError
from ..enums import ConnectionStates, PacketProtocols, Netmodes
from ..type_serialisers import get_serialiser_for
from ..packet import Packet


__all__ = 'ServerHandshakeManager', 'ClientHandshakeManager'


# Handshake Streams
class HandshakeManagerBase:

    def __init__(self, world, connection):
        self.state = ConnectionStates.init

        self.world = world
        self.connection = connection
        self.logger = connection.logger.getChild("HandshakeManager")

        self.replication_manager = None
        self.connection_info = connection.connection_info
        self.remove_connection = None

        # Additional data
        self.netmode_packer = get_serialiser_for(int)
        self.string_packer = get_serialiser_for(str)

        # Register listenerspacket_received
        register_protocol_listeners(self, connection.packet_received)
        self.senders = get_state_senders(self)


class ServerHandshakeManager(HandshakeManagerBase):
    """Manages connection state for the server"""

    def __init__(self, world, connection):
        super().__init__(world, connection)

        self.handshake_error = None

        self.invoke_handshake()

    def on_ack_handshake_failed(self, packet):
        self.world.messenger.send("connection_error", self)

    @on_protocol(PacketProtocols.request_disconnect)
    def receive_disconnect_request(self, data):
        self.state = ConnectionStates.disconnected

        if self.replication_manager is not None:
            self.replication_manager.on_disconnected()

    @on_protocol(PacketProtocols.request_handshake)
    def receive_handshake_request(self, data):
        # Only if we're not already in some handshake process
        if self.state != ConnectionStates.awaiting_handshake:
            return

        try:
            pre_initialise = self.world.rules.pre_initialise

        except AttributeError:
            raise RuntimeError("World is not configured with rules!")

        try:
            pre_initialise(self.connection_info)

        except NetworkError as err:
            self.logger.error("Connection was refused: {}".format(repr(err)))
            self.handshake_error = err

        self.state = ConnectionStates.received_handshake
        self.send_handshake_result()

    def send_handshake_result(self):
        connection_failed = self.handshake_error is not None

        if connection_failed:
            pack_string = self.string_packer.pack
            error_type = self.handshake_error.__class__.__name__

            try:
                error_body = self.handshake_error.args[0]
            except IndexError:
                error_body = ''

            error_data = pack_string(error_type) + pack_string(error_body)

            # Set failed state
            self.state = ConnectionStates.failed
            self.world.messenger.send("connection_error", self)

            # Send result
            packet = Packet(protocol=PacketProtocols.handshake_failed, payload=error_data,
                            on_success=self.on_ack_handshake_failed)

        else:
            # Set success state
            self.state = ConnectionStates.connected
            self.world.messenger.send("connection_success", self)

            # On disconnected for replication manager
            self.replication_manager = ServerReplicationManager(self.world, self.connection)

            # Send result
            packet = Packet(protocol=PacketProtocols.handshake_success, reliable=True)

        # Add to connection queue
        self.connection.queue_packet(packet)

    def invoke_handshake(self):
        """Invoke handshake attempt on client, used for multicasting"""
        self.state = ConnectionStates.awaiting_handshake

        packet = Packet(protocol=PacketProtocols.invoke_handshake, reliable=True)
        self.connection.queue_packet(packet)


class ClientHandshakeManager(HandshakeManagerBase):

    def __init__(self, world, connection):
        super().__init__(world, connection)

        self.invoke_handshake()

    def invoke_handshake(self):
        self.state = ConnectionStates.received_handshake
        packet = Packet(protocol=PacketProtocols.request_handshake, reliable=True)
        self.connection.queue_packet(packet)

    @on_protocol(PacketProtocols.handshake_success)
    def receive_handshake_success(self, data):
        if self.state != ConnectionStates.received_handshake:
            return

        self.state = ConnectionStates.connected
        # Create replication stream
        self.replication_manager = ClientReplicationManager(self.world, self.connection)

        self.world.messenger.send("connection_success", self)

    @on_protocol(PacketProtocols.invoke_handshake)
    def receive_multicast_ping(self, data):
        self.invoke_handshake()

    @on_protocol(PacketProtocols.handshake_failed)
    def receive_handshake_failed(self, packet):
        data = packet.payload

        error_type, type_size = self.string_packer.unpack_from(data)
        error_message, message_size = self.string_packer.unpack_from(data, type_size)

        error_class = NetworkError.subclasses[error_type]
        raised_error = error_class(error_message)

        self.logger.error("Authentication failed: {}".format(repr(raised_error)))
        self.state = ConnectionStates.failed

        self.world.messenger.send("connection_error", error=raised_error, connection=self.connection)


def create_handshake_manager(world, connection):
    if world.netmode == Netmodes.server:
        return ServerHandshakeManager(world, connection)

    else:
        return ClientHandshakeManager(world, connection)
