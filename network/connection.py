from .packet import Packet, PacketCollection
from .handler_interfaces import get_handler
from .descriptors import TypeFlag
from .decorators import netmode_switch
from .replicables import Replicable, WorldInfo
from .signals import (ReplicableUnregisteredSignal, ReplicableRegisteredSignal,
                      SignalListener)
from .enums import Roles, Protocols, Netmodes
from .netmode_switch import NetmodeSwitch
from .channel import Channel

from operator import attrgetter

__all__ = ['Connection', 'ServerConnection', 'ClientConnection']


def consume(iterable):
    """Consumes an iterable
    Iterates over iterable until StopIteration is raised

    :param iterable: Iterable object"""
    for _ in iterable:
        pass


class Connection(SignalListener, NetmodeSwitch):
    """Connection between loacl host and remote peer
    Represents a successful connection"""

    subclasses = {}

    def __init__(self, netmode):
        super().__init__()

        self.netmode = netmode
        self.replicable = None

        self.channels = {}

        self.string_packer = get_handler(TypeFlag(str))
        self.int_packer = get_handler(TypeFlag(int))
        self.replicable_packer = get_handler(TypeFlag(Replicable))

    @ReplicableUnregisteredSignal.global_listener
    def notify_unregistration(self, target):
        """Handles un-registration of a replicable instance
        Deletes channel for replicable instance

        :param target: replicable that was unregistered"""
        self.channels.pop(target.instance_id)

    @ReplicableRegisteredSignal.global_listener
    def notify_registration(self, target):
        """Handles registration of a replicable instance
        Create channel for replicable instance

        :param target: replicable that was registered"""
        self.channels[target.instance_id] = Channel(self, target)

    def on_delete(self):
        """Delete callback"""
        self.replicable.request_unregistration()

    @property
    def prioritised_channels(self):
        """Returns a generator for replicables
        with a remote role != Roles.none

        :yield: replicable, (is_owner and relevant_to_owner), channel"""
        no_role = Roles.none  # @UndefinedVariable

        for channel in sorted(self.channels.values(), reverse=True,
                              key=attrgetter("replication_priority")):
            replicable = channel.replicable

            # Check if remote role is permitted
            if replicable.roles.remote == no_role:
                continue

            # Now check if we are an owner
            yield (channel, replicable.relevant_to_owner
                            and channel.is_owner)

    def get_method_replication(self, replicables, collection, bandwidth):
        """Writes replicated function calls to packet collection

        :param replicables: iterable of replicables to consider replication
        :param collection: PacketCollection instance
        :param bandwidth: available bandwidth
        :yield: each entry in replicables"""
        method_invoke = Protocols.method_invoke  # @UndefinedVariable
        make_packet = Packet
        store_packet = collection.members.append

        for item in replicables:
            channel, is_owner_relevant = item

            # Send RPC calls if we are the owner
            if is_owner_relevant and channel.has_rpc_calls:
                packed_id = channel.packed_id

                for rpc_call, reliable in channel.take_rpc_calls():
                    rpc_data = packed_id + rpc_call

                    store_packet(
                            make_packet(protocol=method_invoke,
                                      payload=rpc_data,
                                      reliable=reliable)
                                )
            yield item

    def received_all(self):
        pass


@netmode_switch(Netmodes.client)
class ClientConnection(Connection):

    def __init__(self, netmode):
        super().__init__(netmode)

        self.pending_notifications = []

    def received_all(self):
        for notification in self.pending_notifications:
            notification()
        self.pending_notifications.clear()

    def set_replication(self, packet):
        '''Replication function
        Accepts replication packets and responds to protocol

        :param packet: replication packet'''

        instance_id = self.replicable_packer.unpack_id(packet.payload)
        payload_following_id = packet.payload[self.replicable_packer.size():]

        # If an update for a replicable
        if packet.protocol == Protocols.replication_update:  # @UndefinedVariable @IgnorePep8
            try:
                channel = self.channels[instance_id]

            except KeyError:
                print("Unable to find network object with id {}"
                      .format(instance_id))

            else:
                # Apply attributes and retrieve notify callback
                notification_callback = channel.set_attributes(payload_following_id)

                # Save callbacks
                if notification_callback:
                    self.pending_notifications.append(notification_callback)

        # If it is an RPC call
        elif packet.protocol == Protocols.method_invoke:  # @UndefinedVariable
            self.received_all()

            try:
                channel = self.channels[instance_id]

            except KeyError:
                print("Unable to find network object with id {}"
                      .format(instance_id))

            else:
                if channel.is_owner:
                    channel.invoke_rpc_call(payload_following_id)

        # If construction for replicable
        elif packet.protocol == Protocols.replication_init:  # @UndefinedVariable @IgnorePep8
            type_name = self.string_packer.unpack_from(payload_following_id)
            type_size = self.string_packer.size(payload_following_id)
            payload_following_id = payload_following_id[type_size:]

            is_connection_host = bool(self.int_packer.unpack_from(
                                                  payload_following_id))

            # Create replicable of same type
            replicable_cls = Replicable.from_type_name(type_name)  # @UndefinedVariable @IgnorePep8
            replicable = Replicable.create_or_return(replicable_cls,
                                          instance_id, register=True)
            # Perform incomplete role switch
            (replicable.roles.local,
             replicable.roles.remote) = (replicable.roles.remote,
                                         replicable.roles.local)
            # If replicable is parent (top owner)
            if is_connection_host:
                # Register as own replicable
                self.replicable = replicable

        # If it is the deletion request
        elif packet.protocol == Protocols.replication_del:  # @UndefinedVariable @IgnorePep8
            # If the replicable exists
            try:
                replicable = Replicable.get_from_graph(instance_id)  # @UndefinedVariable @IgnorePep8

            except LookupError:
                pass

            else:
                replicable.request_unregistration(True)

    def send(self, network_tick, available_bandwidth):
        '''Creates a packet collection of replicated function calls

        :param network_tick: unused argument
        :param available_bandwidth: estimated available bandwidth
        :returns: PacketCollection instance'''
        collection = PacketCollection()
        replicables = self.get_method_replication(
                                          self.prioritised_channels,
                                          collection,
                                          available_bandwidth)

        # Consume iterable
        consume(replicables)
        return collection

    def receive(self, packet):
        '''Handles incoming PacketCollection instance

        :param packets: PacketCollection instance'''
        if packet.protocol in Protocols:
            self.set_replication(packet)


@netmode_switch(Netmodes.server)
class ServerConnection(Connection):

    def __init__(self, netmode):
        super().__init__(netmode)

        self.cached_packets = set()

    def on_delete(self):
        '''Callback for connection deletion
        Called by ConnectionStatus when deleted'''
        super().on_delete()

        # If we own a controller destroy it
        if self.replicable:
            # We must be connected to have a controller
            print("{} disconnected!".format(self.replicable))
            self.replicable.request_unregistration()

    @ReplicableUnregisteredSignal.global_listener
    def notify_unregistration(self, target):
        '''Called when replicable dies

        :param replicable: replicable that died'''

        # If the target is not in channel list, we don't need to delete
        if not target.instance_id in self.channels:
            return

        channel = self.channels[target.instance_id]
        packet = Packet(protocol=Protocols.replication_del,  # @UndefinedVariable @IgnorePep8
                        payload=channel.packed_id, reliable=True)
        # Send delete packet
        self.cached_packets.add(packet)

        super().notify_unregistration(target)

    def get_attribute_replication(self, replicables, collection,
                                  bandwidth, send_attributes=True):
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

        replication_init = Protocols.replication_init  # @UndefinedVariable
        replication_update = Protocols.replication_update  # @UndefinedVariable

        timestamp = WorldInfo.elapsed
        is_relevant = WorldInfo.rules.is_relevant
        connection_replicable = self.replicable

        used_bandwidth = 0
        free_bandwidth = bandwidth > 0

        for item in replicables:

            if not free_bandwidth:
                yield item
                continue

            channel, is_owner = item

            # Get replicable
            replicable = channel.replicable

            # Only send attributes if relevant
            if not (channel.awaiting_replication and
                    (is_owner or is_relevant(connection_replicable,
                                             replicable))):
                continue

            # Get network ID
            packed_id = channel.packed_id

            # If we've never replicated to this channel
            if channel.is_initial:
                # Pack the class name
                packed_class = self.string_packer.pack(
                               replicable.__class__.type_name)
                packed_is_host = self.int_packer.pack(
                              replicable == self.replicable)

                # Send the protocol, class name and owner status to client
                packet = make_packet(protocol=replication_init,
                              payload=packed_id + packed_class +\
                              packed_is_host, reliable=True)
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

                    packet = make_packet(
                                        protocol=replication_update,
                                        payload=update_payload,
                                        reliable=True)

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
        '''Handles incoming PacketCollection instance

        :param packets: PacketCollection instance'''
        # Local space variables
        channels = self.channels

        unpacker = self.replicable_packer.unpack_id
        id_size = self.replicable_packer.size()

        method_invoke = Protocols.method_invoke  # @UndefinedVariable

        # If it is an RPC packet
        if packet.protocol == method_invoke:
            # Unpack data
            instance_id = unpacker(packet.payload)
            channel = channels[instance_id]

            # If we have permission to execute
            if channel.is_owner:
                channel.invoke_rpc_call(packet.payload[id_size:])

    def send(self, network_tick, available_bandwidth):
        '''Creates a packet collection of replicated function calls

        :param network_tick: non urgent data is included in collection
        :param available_bandwidth: estimated available bandwidth
        :returns: PacketCollection instance'''

        collection = PacketCollection()
        replicables = self.prioritised_channels

        replicables = self.get_attribute_replication(replicables,
                                                         collection,
                                                         available_bandwidth,
                                                         network_tick)
        replicables = self.get_method_replication(
                                          replicables,
                                          collection,
                                          available_bandwidth)

        # Consume iterable
        consume(replicables)
        return collection
