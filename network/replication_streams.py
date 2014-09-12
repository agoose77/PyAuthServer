from .signals import *
from .streams import Dispatcher, InjectorStream


class ServerReplicationStream(SignalListener):

    def __init__(self):
        self.register_signals()

        self.channels = {}
        self.dispatcher = Dispatcher()

        self.removal_stream = self.dispatcher.create_stream(InjectorStream)
        self.creation_stream = self.dispatcher.create_stream(InjectorStream)
        self.attributes_stream = self.dispatcher.create_stream(InjectorStream)
        self.method_stream = self.dispatcher.create_stream(InjectorStream)

    def pull_packets(self, network_tick, bandwidth):
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
                self.creation_stream.queue.append(packet)

                used_bandwidth += packet.size

            # Send changed attributes
            if network_tick or channel.is_initial:
                attributes = channel.get_attributes(is_owner)

                # If they have changed
                if attributes:
                    # This ensures references exist
                    # By calling it after all creation packets are yielded
                    update_payload = packed_id + attributes

                    packet = make_packet(protocol=replication_update, payload=update_payload, reliable=True)

                    self.attributes_stream.queue.append(packet)
                    used_bandwidth += packet.size

                # If a temporary replicable remove from channels (but don't delete)
                if replicable.replicate_temporarily:
                    self.channels.pop(replicable.instance_id)

        return self.dispatcher.pull_packets(network_tick, bandwidth)



