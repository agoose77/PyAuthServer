from .streams import response_protocol, ProtocolHandler
from .latency_calculator import LatencyCalculator

from ..channel import Channel
from ..decorators import with_tag
from ..enums import ConnectionProtocols, Netmodes, Roles
from ..handlers import get_handler
from ..logger import logger
from ..packet import Packet, PacketCollection
from ..replicable import Replicable
from ..signals import (Signal, SignalListener, ReplicableRegisteredSignal, ReplicableUnregisteredSignal,
                       LatencyUpdatedSignal)
from ..tagged_delegate import DelegateByNetmode
from ..type_flag import TypeFlag
from ..world_info import WorldInfo

from functools import partial
from operator import attrgetter

__all__ = "ReplicationStream", "ServerReplicationStream", "ClientReplicationStream"


# Replication Streams
class ReplicationStream(SignalListener, ProtocolHandler, DelegateByNetmode):
    subclasses = {}

    def __init__(self, dispatcher):
        self.channels = {}
        self.replicable = None

        self.string_packer = get_handler(TypeFlag(str))
        self.int_packer = get_handler(TypeFlag(int))
        self.bool_packer = get_handler(TypeFlag(bool))
        self.replicable_packer = get_handler(TypeFlag(Replicable))

        self.method_queue = []

        self.load_existing_replicables()

        # Call this last to ensure we intercept registration callbacks at the correct time
        self.register_signals()
        Signal.update_graph()

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

    @response_protocol(ConnectionProtocols.invoke_method)
    def handle_method_call(self, data):

        # Unpack data
        instance_id, id_size = self.replicable_packer.unpack_id(data)
        channel = self.channels[instance_id]

        # If we have permission to execute
        if channel.is_owner:
            channel_data = data[id_size:]
            channel.invoke_rpc_call(channel_data)

    @ReplicableUnregisteredSignal.on_global
    def notify_unregistered(self, target):
        """Handles un-registered of a replicable instance
        Deletes channel for replicable instance

        :param target: replicable that was unregistered
        """
        self.channels.pop(target.instance_id)

    @ReplicableRegisteredSignal.on_global
    def notify_registered(self, target):
        """Handles registered of a replicable instance
        Create channel for replicable instance

        :param target: replicable that was registered
        """
        self.channels[target.instance_id] = Channel(self, target)

    def load_existing_replicables(self):
        """Load existing registered replicables"""
        for replicable in Replicable:
            self.notify_registered(replicable)

    def send_method_calls(self, replicables, available_bandwidth):
        """Creates a packet collection of replicated function calls

        :param available_bandwidth: estimated available bandwidth
        :returns: PacketCollection instance
        """
        for item in replicables:
            channel, is_and_relevant_to_owner = item

            # Only send attributes if relevant
            if not (is_and_relevant_to_owner and channel.has_rpc_calls):
                continue

            self.write_method_calls(channel)

    def write_method_calls(self, channel):
        packed_id = channel.packed_id
        method_invoke_protocol = ConnectionProtocols.invoke_method
        packets = [Packet(protocol=method_invoke_protocol, payload=packed_id + rpc_call, reliable=reliable)
                   for rpc_call, reliable in channel.take_rpc_calls()]

        self.method_queue.extend(packets)


@with_tag(Netmodes.server)
class ServerReplicationStream(ReplicationStream):

    def __init__(self, dispatcher):
        super().__init__(dispatcher)

        self.removal_queue = []
        self.creation_queue = []
        self.attribute_queue = []

        self.queues = self.removal_queue, self.creation_queue, self.attribute_queue, self.method_queue

        self.replicable = WorldInfo.rules.post_initialise(self)

        self.latency_calculator = LatencyCalculator()
        self.latency_calculator.on_updated = partial(LatencyUpdatedSignal.invoke, target=self.replicable)

    def get_ack_latency_wrapper(self, callback):
        """Wraps callback with latency calculator callback

        :param callback: callback used to stop timing
        """
        def _wrapper(packet):
            if callable(callback):
                callback(packet)

            self.latency_calculator.stop_sample(packet)

        return _wrapper

    def on_disconnected(self):
        WorldInfo.rules.post_disconnect(self, self.replicable)

    @ReplicableUnregisteredSignal.on_global
    def notify_unregistered(self, target):
        """Called when replicable dies

        :param target: replicable that was unregistered
        """

        # If the target is not in channel list, we don't need to delete
        if target.instance_id not in self.channels:
            return

        channel = self.channels[target.instance_id]
        self.write_removal(channel)

        super().notify_unregistered(target)

    def send_attributes(self, replicables, available_bandwidth):
        """Creates a packet collection of replicated function calls and attributes

        :param available_bandwidth: estimated available bandwidth
        :returns: PacketCollection instance
        """
        is_relevant = WorldInfo.rules.is_relevant
        connection_replicable = self.replicable

        for item in replicables:
            channel, is_and_relevant_to_owner = item

            # Get replicable
            replicable = channel.replicable

            # Only send attributes if relevant
            if not (channel.awaiting_replication and (is_and_relevant_to_owner or
                                                      is_relevant(connection_replicable, replicable))):
                continue

            # If we've never replicated to this channel
            if channel.is_initial:
                # Pack the class name
                self.write_creation(channel)

            # Send changed attributes
            self.write_attributes(channel, is_and_relevant_to_owner)

            # If a temporary replicable remove from channels (but don't delete)
            if replicable.replicate_temporarily:
                self.channels.pop(replicable.instance_id)

            yield item

    def pull_packets(self, network_tick, bandwidth):
        replicables = self.prioritised_channels

        if network_tick:
            replicables = self.send_attributes(replicables, bandwidth)

        self.send_method_calls(replicables, bandwidth)

        members = []

        for queue in self.queues:
            members.extend(queue)
            queue.clear()

        if not members:
            return None

        packets = PacketCollection()
        packets.members = members

        packet = members[0]
        packet.on_success = self.get_ack_latency_wrapper(packet.on_success)

        self.latency_calculator.start_sample(packet)

        return packets

    def write_attributes(self, channel, is_owner):
        attributes = channel.get_attributes(is_owner)

        # If they have changed
        if not attributes:
            return

        update_payload = channel.packed_id + attributes
        packet = Packet(protocol=ConnectionProtocols.attribute_update, payload=update_payload, reliable=True)
        self.attribute_queue.append(packet)

    def write_creation(self, channel):
        replicable = channel.replicable

        packed_class = self.string_packer.pack(replicable.__class__.type_name)
        packed_is_host = self.bool_packer.pack(replicable == self.replicable)

        # Send the protocol, class name and owner status to client
        payload = channel.packed_id + packed_class + packed_is_host
        packet = Packet(protocol=ConnectionProtocols.replication_init, payload=payload, reliable=True)
        self.creation_queue.append(packet)

    def write_removal(self, channel):
        packet = Packet(protocol=ConnectionProtocols.replication_del, payload=channel.packed_id, reliable=True)
        self.removal_queue.append(packet)


@with_tag(Netmodes.client)
class ClientReplicationStream(ReplicationStream):

    def __init__(self, dispatcher):
        super().__init__(dispatcher)

        self.pending_notifications = []

    @response_protocol(ConnectionProtocols.replication_init)
    def handle_replication_init(self, data):
        instance_id, id_size = self.replicable_packer.unpack_id(data)
        offset = id_size

        type_name, type_size = self.string_packer.unpack_from(data, offset=offset)
        offset += type_size

        is_connection_host, _ = self.bool_packer.unpack_from(data, offset=offset)

        # Find replicable class
        replicable_cls = Replicable.from_type_name(type_name)
        # Create replicable of same type
        replicable = replicable_cls.create_or_return(instance_id, register_immediately=True)
        # If replicable is parent (top owner)
        if is_connection_host:
            # Register as own replicable
            self.replicable = replicable

    @response_protocol(ConnectionProtocols.attribute_update)
    def handle_replication_update(self, data):
        instance_id, id_size = self.replicable_packer.unpack_id(data)

        try:
            channel = self.channels[instance_id]

        except KeyError:
            logger.exception("Unable to find channel for network object with id {}".format(instance_id))

        else:
            # Apply attributes and retrieve notify callback
            notification_callback = channel.set_attributes(data, offset=id_size)

            # Save callbacks
            if notification_callback:
                self.pending_notifications.append(notification_callback)

    @response_protocol(ConnectionProtocols.replication_del)
    def handle_replication_delete(self, data):
        instance_id, _ = self.replicable_packer.unpack_id(data)

        try:
            replicable = Replicable.get_from_graph(instance_id)

        except LookupError:
            pass

        else:
            replicable.deregister(True)

    def handle_packets(self, packet_collection):
        super().handle_packets(packet_collection)

        for notification in self.pending_notifications:
            notification()

        self.pending_notifications.clear()

    def on_disconnected(self):
        for replicable in WorldInfo.replicables:
            if replicable.is_static:
                continue

            replicable.deregister()

    def pull_packets(self, network_tick, bandwidth):
        replicables = self.prioritised_channels
        self.send_method_calls(replicables, bandwidth)

        members = self.method_queue

        if not members:
            return None

        packets = PacketCollection()
        packets.members.extend(members)
        members.clear()

        return packets
