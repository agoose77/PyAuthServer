from .streams import on_protocol, register_protocol_listeners
from .latency_calculator import LatencyCalculator

from ..channel import ChannelBase
from ..enums import PacketProtocols, Roles
from ..handlers import get_handler
from ..packet import Packet, PacketCollection
from ..replicable import Replicable
from ..signals import (SignalListener, ReplicableRegisteredSignal, ReplicableUnregisteredSignal, LatencyUpdatedSignal)
from ..scene import NetworkScene
from ..type_flag import TypeFlag
from ..world_info import WorldInfo

from functools import partial
from operator import attrgetter

__all__ = "SceneReplicationManagerBase", "ServerSceneReplicationManager", "ClientSceneReplicationManager"


# Replication Streams
class SceneReplicationManagerBase(SignalListener):

    def __init__(self, connection):
        self.scene_channels = {}
        self.connection = connection
        self.replicable = None

        self.logger = connection.logger.getChild("ReplicationManager")

        self.string_packer = get_handler(TypeFlag(str))
        self.int_packer = get_handler(TypeFlag(int))
        self.bool_packer = get_handler(TypeFlag(bool))
        self.replicable_packer = get_handler(TypeFlag(Replicable))

        self.method_queue = []

        self.load_existing_replicables()

        # Call this last to ensure we intercept registration callbacks at the correct time
        self.register_signals()

        register_protocol_listeners(self, connection.dispatcher)

    @property
    def prioritised_channels(self):
        """Returns a generator for replicables
        with a remote role != Roles.none

        :yield: replicable, (is_owner and relevant_to_owner), channel
        """
        no_role = Roles.none  # @UndefinedVariable
        # TODO move this
        for channel in sorted(self.channels.values(), reverse=True, key=attrgetter("replication_priority")):
            replicable = channel.replicable

            # Check if remote role is permitted
            if replicable.roles.remote == no_role:
                continue

            yield channel, replicable.relevant_to_owner and channel.is_owner

    @on_protocol(PacketProtocols.invoke_method)
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
        self.channels[target.instance_id] = ChannelBase(self, target)

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
        method_invoke_protocol = PacketProtocols.invoke_method
        packets = [Packet(protocol=method_invoke_protocol, payload=packed_id + rpc_call, reliable=reliable)
                   for rpc_call, reliable in channel.dump_rpc_calls()]

        self.method_queue.extend(packets)


class ServerSceneReplicationManager(SceneReplicationManagerBase):

    def __init__(self, connection):
        super().__init__(connection)

        self.removal_queue = []
        self.creation_queue = []
        self.attribute_queue = []

        self.packet_queues = self.removal_queue, self.creation_queue, self.attribute_queue, self.method_queue

        self.replicable = WorldInfo.rules.post_initialise(self)

        self.latency_calculator = LatencyCalculator()
        self.latency_calculator.on_updated = partial(LatencyUpdatedSignal.invoke, target=self.replicable)

    def _get_ack_latency_wrapper(self, callback):
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
            if not (channel.awaiting_replication
                    and (is_and_relevant_to_owner or
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

    def send(self, network_tick):
        replication_tuples = self.prioritised_channels
        bandwidth = self.connection.bandwidth

        if network_tick:
            replication_tuples = self.send_attributes(replication_tuples, bandwidth)

        self.send_method_calls(replication_tuples, bandwidth)

        # Collate all queues
        packets = []
        for queue in self.packet_queues:
            packets.extend(queue)
            queue.clear()

        if not packets:
            return None

        packet_collection = PacketCollection(packets)

        first_packet = packets[0]

        # Start RTT calculation
        self.latency_calculator.start_sample(first_packet)

        # Stop calculating RTT when ACKED
        existing_on_success = first_packet.on_success
        first_packet.on_success = self._get_ack_latency_wrapper(existing_on_success)

        packets.clear()

        return packet_collection

    def write_attributes(self, channel, is_owner):
        attributes = channel.get_attributes(is_owner)

        # If they have changed
        if not attributes:
            return

        update_payload = channel.packed_id + attributes
        packet = Packet(protocol=PacketProtocols.attribute_update, payload=update_payload, reliable=True)
        self.attribute_queue.append(packet)

    def write_creation(self, channel):
        replicable = channel.replicable

        packed_class = self.string_packer.pack(replicable.__class__.type_name)
        packed_is_host = self.bool_packer.pack(replicable == self.replicable)

        # Send the protocol, class name and owner status to client
        payload = channel.packed_id + packed_class + packed_is_host
        packet = Packet(protocol=PacketProtocols.replication_init, payload=payload, reliable=True)
        self.creation_queue.append(packet)

    def write_removal(self, channel):
        packet = Packet(protocol=PacketProtocols.replication_del, payload=channel.packed_id, reliable=True)
        self.removal_queue.append(packet)


class ClientSceneReplicationManager(SceneReplicationManagerBase):

    def __init__(self, connection):
        super().__init__(connection)

        self.pending_notifications = []

        # After receiving packets is done, we need to send attribute notifications
        self.connection.post_receive_callbacks.append(self.post_receive)

    @on_protocol(PacketProtocols.replication_init)
    def handle_replication_init(self, data):
        instance_id, id_size = self.replicable_packer.unpack_id(data)
        offset = id_size

        type_name, type_size = self.string_packer.unpack_from(data, offset=offset)
        offset += type_size

        is_connection_host, _ = self.bool_packer.unpack_from(data, offset=offset)

        # Find replicable class
        replicable_cls = Replicable.from_type_name(type_name)
        # Create replicable of same type
        replicable = replicable_cls.create_or_return(instance_id)
        # If replicable is parent (top owner)
        if is_connection_host:
            # Register as own replicable
            self.replicable = replicable

    @on_protocol(PacketProtocols.attribute_update)
    def handle_replication_update(self, data):
        instance_id, id_size = self.replicable_packer.unpack_id(data)

        try:
            channel = self.channels[instance_id]

        except KeyError:
            self.logger.exception("Unable to find channel for network object with id {}".format(instance_id))

        else:
            # Apply attributes and retrieve notify callback
            notification_callback = channel.set_attributes(data, offset=id_size)

            # Save callbacks
            if notification_callback:
                self.pending_notifications.append(notification_callback)

    @on_protocol(PacketProtocols.replication_del)
    def handle_replication_delete(self, data):
        instance_id, _ = self.replicable_packer.unpack_id(data)

        try:
            replicable = Replicable[instance_id]

        except KeyError:
            pass

        else:
            replicable.deregister()

    def post_receive(self):
        # TODO call this in gameloop
        """Called after network receives incoming packets"""
        for notification in self.pending_notifications:
            notification()

        self.pending_notifications.clear()

    def on_disconnected(self):
        # Unregister replicables created by server on client
        for replicable in list(Replicable):
            if replicable.is_static:
                continue

            replicable.deregister()

    def send(self, network_tick):
        replicables = self.prioritised_channels
        bandwidth = self.connection.bandwidth

        self.send_method_calls(replicables, bandwidth)

        packets = self.method_queue
        if not packets:
            return None

        packet_collection = PacketCollection(packets)
        packets.clear()

        return packet_collection
