from .channel import Channel
from .conditions import is_annotatable
from .decorators import with_tag, get_annotation, set_annotation
from .type_flag import TypeFlag
from .errors import NetworkError
from .enums import ConnectionStatus, ConnectionProtocols, Roles, Netmodes
from .handler_interfaces import get_handler
from .logger import logger
from .tagged_delegate import DelegateByNetmode
from .type_register import TypeRegister
from .packet import Packet, PacketCollection
from .replicable import Replicable
from .signals import *
from .world_info import WorldInfo

from inspect import getmembers
from operator import attrgetter

__all__ = ['Connection', 'ServerConnection', 'ClientConnection']

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

    def handle_packet(self, packet):
        for stream in self.streams:
            stream.handle_packet(packet)

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
    def handle_packet(packet):
        """Non functional packet handling method

        :param packet: Packet instance
        """
        return


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

    def handle_packet(self, packet):
        """Lookup the appropriate handler for given packet type

        :param packet: Packet instance
        """
        try:
            handler = self.__class__.receivers[packet.protocol]

        except KeyError:
            return

        handler(self, packet.payload)


class StatusDispatcher(metaclass=TypeRegister):
    """Dispatches packets according to current state"""

    def __init__(self):
        self.status = ConnectionStatus.pending

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


# Handshake Streams
class HandshakeStream(ProtocolHandler, StatusDispatcher, DelegateByNetmode):
    subclasses = {}

    def __init__(self, dispatcher):
        self.dispatcher = dispatcher

        # Additional data
        self.netmode_packer = get_handler(TypeFlag(int))
        self.string_packer = get_handler(TypeFlag(str))


@with_tag(Netmodes.server)
class ServerHandshakeStream(HandshakeStream):
    """Manages connection state for the server"""

    def __init__(self, dispatcher):
        super().__init__(dispatcher)

        self.handshake_error = None

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
            self.dispatcher.create_stream(ReplicationStream)

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
class ClientHandshakeStream(HandshakeStream):

    @send_state(ConnectionStatus.pending)
    def send_handshake_request(self, network_tick, bandwidth):
        self.status = ConnectionStatus.handshake

        netmode_data = self.netmode_packer.pack(WorldInfo.netmode)
        return Packet(protocol=ConnectionProtocols.handshake_request, payload=netmode_data)

    @response_protocol(ConnectionProtocols.handshake_success)
    def receive_handshake_success(self, data):
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


# Replication Streams
class ReplicationStream(SignalListener, ProtocolHandler, StatusDispatcher, DelegateByNetmode):
    subclasses = {}

    def __init__(self, dispatcher):
        self.register_signals()

        self.channels = {}
        self.replicable = None

        self.string_packer = get_handler(TypeFlag(str))
        self.int_packer = get_handler(TypeFlag(int))
        self.bool_packer = get_handler(TypeFlag(bool))
        self.replicable_packer = get_handler(TypeFlag(Replicable))

        self._latency = 0.0

    @property
    def latency(self):
        return self._latency

    @latency.setter
    def latency(self, latency):
        self._latency = latency

        LatencyUpdatedSignal.invoke(self.latency, target=self.replicable)

    @ReplicableUnregisteredSignal.global_listener
    def notify_unregistration(self, target):
        """Handles un-registration of a replicable instance
        Deletes channel for replicable instance

        :param target: replicable that was unregistered
        """
        self.channels.pop(target.instance_id)

    # todo rename registration to registered
    @ReplicableRegisteredSignal.global_listener
    def notify_registration(self, target):
        """Handles registration of a replicable instance
        Create channel for replicable instance

        :param target: replicable that was registered
        """
        if not target.registered:
            return

        self.channels[target.instance_id] = Channel(self, target)

    def on_delete(self):
        """Delete callback"""
        self.replicable.request_unregistration()

    @property
    def prioritised_channels(self):
        """Returns a generator for replicables
        with a remote role != Roles.none

        :yield: replicable, (is_owner and relevant_to_owner), channel
        """
        no_role = Roles.none  # @UndefinedVariable

        for channel in sorted(self.channels.values(), reverse=True, key=attrgetter("replication_priority")):
            replicable = channel.replicable

            # Check if remote role is permitted
            if replicable.roles.remote == no_role:
                continue

            yield channel, replicable.relevant_to_owner and channel.is_owner

    @staticmethod
    def write_replicated_method_calls(replicables, collection, bandwidth):
        """Writes replicated function calls to packet collection

        :param replicables: iterable of replicables to consider replication
        :param collection: PacketCollection instance
        :param bandwidth: available bandwidth
        :yield: each entry in replicables
        """
        method_invoke = ConnectionProtocols.method_invoke  # @UndefinedVariable
        make_packet = Packet
        store_packet = collection.members.append

        for item in replicables:
            channel, is_owner_relevant = item

            # Send RPC calls if we are the owner
            if is_owner_relevant and channel.has_rpc_calls:
                packed_id = channel.packed_id

                for rpc_call, reliable in channel.take_rpc_calls():
                    rpc_data = packed_id + rpc_call

                    store_packet(make_packet(protocol=method_invoke, payload=rpc_data, reliable=reliable))
            yield item


@with_tag(Netmodes.server)
class ServerReplicationStream(Dispatcher, ReplicationStream):

    def __init__(self, dispatcher):
        super().__init__()
        self.replicable = WorldInfo.rules.post_initialise(self)
        # Replicable is boolean false until registered
        # User can force register though!

        # Rename / reimplement
        self.cached_packets = set()

    @ReplicableUnregisteredSignal.global_listener
    def notify_unregistration(self, target):
        """Called when replicable dies

        :param target: replicable that was unregistered
        """

        # If the target is not in channel list, we don't need to delete
        if not target.instance_id in self.channels:
            return

        channel = self.channels[target.instance_id]
        packet = Packet(protocol=ConnectionProtocols.replication_del, payload=channel.packed_id, reliable=True)
        # Send delete packet
        self.cached_packets.add(packet)

        super().notify_unregistration(target)

    def write_replicated_attributes(self, replicables, collection, bandwidth, send_attributes=True):
        """Generator
        Writes to packet collection, respecting bandwidth for attribute
        replication

        :param replicables: iterable of replicables to consider replication
        :param collection: PacketCollection instance
        :param bandwidth: available bandwidth
        :yield: each entry in replicables"""

        make_packet = Packet
        store_packet = collection.members.append
        insert_packet = collection.members.insert

        replication_init = ConnectionProtocols.replication_init
        replication_update = ConnectionProtocols.replication_update

        is_relevant = WorldInfo.rules.is_relevant
        connection_replicable = self.replicable

        used_bandwidth = 0
        free_bandwidth = bandwidth > 0

        replicables = list(replicables)

        for item in replicables:

            if not free_bandwidth:
                yield item
                continue

            channel, is_owner = item

            # Get replicable
            replicable = channel.replicable

            # Only send attributes if relevant
            if not (channel.awaiting_replication and (is_owner or is_relevant(connection_replicable, replicable))):
                continue

            # Get network ID
            packed_id = channel.packed_id

            # If we've never replicated to this channel
            if channel.is_initial:
                # Pack the class name
                packed_class = self.string_packer.pack(replicable.__class__.type_name)
                packed_is_host = self.bool_packer.pack(replicable == self.replicable)

                # Send the protocol, class name and owner status to client
                packet = make_packet(protocol=replication_init, payload=packed_id + packed_class + packed_is_host,
                                     reliable=True)
                # Insert the packet at the front (to ensure attribute
                # references are valid to newly created replicables
                insert_packet(0, packet)

                used_bandwidth += packet.size

            # Send changed attributes
            if send_attributes or channel.is_initial:
                attributes = channel.get_attributes(is_owner)

                # If they have changed
                if attributes:
                    # This ensures references exist
                    # By calling it after all creation packets are yielded
                    update_payload = packed_id + attributes

                    packet = make_packet(protocol=replication_update, payload=update_payload, reliable=True)

                    store_packet(packet)
                    used_bandwidth += packet.size

                # If a temporary replicable remove from channels (but don't delete)
                if replicable.replicate_temporarily:
                    self.channels.pop(replicable.instance_id)

            yield item

        # Add queued packets to front of collection
        if self.cached_packets:
            collection.members[:0] = self.cached_packets
            self.cached_packets.clear()

    def receive(self, packet):
        """Handles incoming Packet from client

        :param packet: Packet instance
        """
        # Local space variables
        channels = self.channels

        unpacker = self.replicable_packer.unpack_id
        method_invoke = ConnectionProtocols.method_invoke

        # If it is an RPC packet
        if packet.protocol != method_invoke:
            return

        # Unpack data
        instance_id, id_size = unpacker(packet.payload)
        channel = channels[instance_id]

        # If we have permission to execute
        if channel.is_owner:
            channel_data = packet.payload[id_size:]
            channel.invoke_rpc_call(channel_data)

    def send(self, network_tick, available_bandwidth):
        """Creates a packet collection of replicated function calls

        :param network_tick: non urgent data is included in collection
        :param available_bandwidth: estimated available bandwidth
        :returns: PacketCollection instance
        """

        collection = PacketCollection()
        replicables = self.prioritised_channels

        replicables = self.write_replicated_attributes(replicables, collection, available_bandwidth, network_tick)
        replicables = self.write_replicated_method_calls(replicables, collection, available_bandwidth)

        # Consume iterable
        consume(replicables)
        return collection