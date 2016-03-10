from collections import defaultdict

from ...errors import ExplicitReplicableIdCollisionError
from ...streams.replication.channels import ServerSceneChannel, ClientSceneChannel, SceneChannelBase, \
    ReplicableChannelBase
from ...enums import PacketProtocols, Roles
from ...type_serialisers import get_serialiser_for
from ...packet import Packet, PacketCollection
from ...replicable import Replicable
from ..helpers import on_protocol, register_protocol_listeners


def pack_variable_array(serialiser, array):
    byte_strings = []
    append = byte_strings.append
    pack = serialiser.pack

    for data in array:
        append(pack(len(data)))
        append(data)

    return b''.join(byte_strings)


def unpack_variable_array(serialiser, bytes):
    items = []
    unpack_from = serialiser.unpack_from

    while bytes:
        length, read_bytes = unpack_from(bytes)
        item = bytes[read_bytes: length + read_bytes]
        bytes = bytes[read_bytes+length:]
        items.append(item)

    return items


# TODO Scene and Replicable channels must use packet ACK to enable further replication

class ReplicationManagerBase:

    channel_class = None

    def __init__(self, world, connection):
        self.connection = connection
        self.world = world

        self.scene_channels = {}
        self.logger = connection.logger.getChild("ReplicationManager")

        # For length-delimited arrays
        self._array_length_serialiser = get_serialiser_for(int)

        # Listen to packets from connection
        register_protocol_listeners(self, connection.packet_received)

        connection.pre_send_callbacks.append(self.send)
        connection.latency_calculator.on_updated = self.on_latency_estimate_rtt

    def on_latency_estimate_rtt(self, rtt):
        for scene_channel in self.scene_channels.values():
            if scene_channel.root_replicable:
                scene_channel.root_replicable.messenger.send("estimated_rtt", rtt)

    @on_protocol(PacketProtocols.invoke_method)
    def on_invoke_methods(self, packet):
        payload = packet.payload

        scene_id, offset = SceneChannelBase.id_handler.unpack_from(payload)

        scene_channel = self.scene_channels[scene_id]

        scene = scene_channel.scene
        replicable_channels = scene_channel.replicable_channels
        root_replicable = scene_channel.root_replicable

        replicable_id_handler = ReplicableChannelBase.id_handler
        array_length_serialiser = self._array_length_serialiser

        with replicable_id_handler.current_scene_as(scene):
            method_data_array = unpack_variable_array(array_length_serialiser, payload[offset:])
            for method_data in method_data_array:
                unique_id, id_size = replicable_id_handler.unpack_id(method_data)

                try:
                    replicable_channel = replicable_channels[unique_id]

                except KeyError:
                    self.logger.error("Couldn't find channel for {}".format(unique_id))
                    continue

                replicable = replicable_channel.replicable

                allow_execute = replicable.replicate_to_owner and replicable.root is root_replicable
                replicable_channel.process_rpc_calls(method_data, id_size, allow_execute=allow_execute)

    def send(self, is_network_tick):
        raise NotImplementedError()


class ServerReplicationManager(ReplicationManagerBase):

    channel_class = ServerSceneChannel

    def __init__(self, world, connection):
        super().__init__(world, connection)

        self.deleted_channels = []

        self._string_handler = get_serialiser_for(str)
        self._bool_handler = get_serialiser_for(bool)

        self.scene_id_counter = 0
        self.scene_to_scene_id = {}

        self.register_existing_scenes()

        world.messenger.add_subscriber("scene_added", self.on_scene_added)
        world.messenger.add_subscriber("scene_removed", self.on_scene_removed)

        # On disconnected
        connection.timeout_callbacks.append(self.on_disconnected)

        # Register root replicables
        world.rules.post_initialise(self)

    def on_disconnected(self):
        root_replicables = tuple([s.root_replicable for s in self.scene_channels.values() if s.root_replicable])
        self.world.rules.on_disconnected(self, root_replicables)

    def get_root_for_scene(self, scene):
        scene_id = self.scene_to_scene_id[scene]
        scene_channel = self.scene_channels[scene_id]
        return scene_channel.root_replicable

    def set_root_for_scene(self, scene, replicable):
        """Assign replicable as root for the containing scene

        :param replicable: replicable object or None
        """
        if replicable is not None:
            if scene is not replicable.scene:
                raise ValueError("Replicable does not belong to given scene")

        scene_id = self.scene_to_scene_id[scene]
        scene_channel = self.scene_channels[scene_id]
        scene_channel.root_replicable = replicable

    def register_existing_scenes(self):
        """Load existing registered scenes"""
        for scene in self.world.scenes.values():
            self.on_scene_added(scene)

    def on_scene_added(self, scene):
        scene_id = self.scene_id_counter
        self.scene_id_counter += 1

        self.scene_channels[scene_id] = self.channel_class(self.connection, scene, scene_id)
        self.scene_to_scene_id[scene] = scene_id

    def on_scene_removed(self, scene):
        scene_id = self.scene_to_scene_id.pop(scene)
        channel = self.scene_channels.pop(scene_id)
        self.deleted_channels.append(channel)

    def send(self, is_network_tick):
        pack_string = self._string_handler.pack
        pack_bool = self._bool_handler.pack
        array_length_serialiser = self._array_length_serialiser

        is_relevant = self.world.rules.is_relevant

        queue_packet = self.connection.queue_packet

        for scene_id, scene_channel in self.scene_channels.items():
            # Reliable
            creation_data = []
            deleted_data = []

            # Reliable packets
            reliable_invoke_method_data = []

            # Unreliable packets
            unreliable_invoke_method_data = []
            attribute_data = []

            no_role = Roles.none
            root_replicable = scene_channel.root_replicable

            for replicable_channel in scene_channel.prioritised_channels:
                replicable = replicable_channel.replicable

                # Check if remote role is permitted
                if replicable.roles.remote == no_role:
                    continue

                is_owner = replicable.root is root_replicable
                is_and_relevant_to_owner = replicable.replicate_to_owner and is_owner

                # Write RPC calls
                if is_owner:
                    reliable_rpc_calls, unreliable_rpc_calls = replicable_channel.dump_rpc_calls()

                    if reliable_rpc_calls:
                        reliable_invoke_method_data.append(replicable_channel.packed_id + reliable_rpc_calls)

                    if unreliable_rpc_calls:
                        unreliable_invoke_method_data.append(replicable_channel.packed_id + unreliable_rpc_calls)

                if replicable_channel.is_awaiting_replication and \
                        (is_and_relevant_to_owner or is_relevant(replicable)):

                    # Channel just created
                    if replicable_channel.is_initial:
                        packed_class = pack_string(replicable.__class__.__name__)
                        packed_is_host = pack_bool(replicable is root_replicable)

                        # Send the protocol, class name and owner status to client
                        creation_payload = replicable_channel.packed_id + packed_class + packed_is_host
                        creation_data.append(creation_payload)

                    # Channel attributes
                    serialised_attributes = replicable_channel.get_attributes(is_and_relevant_to_owner)
                    if serialised_attributes:
                        attribute_payload = replicable_channel.packed_id + serialised_attributes
                        attribute_data.append(attribute_payload)

                # Stop replication this replicable
                if replicable.replicate_temporarily:
                    scene_channel.replicable_channels.pop(replicable)

            for replicable_channel in scene_channel.deleted_channels:
                # Send the replicable
                destroyed_payload = replicable_channel.packed_id
                deleted_data.append(destroyed_payload)

            # Clear channels
            scene_channel.deleted_channels.clear()

            # Now construct and ultimately queue packets
            queued_packets = []

            is_new_scene = scene_channel.is_initial
            if is_new_scene:
                packed_name = pack_string(scene_channel.scene.name)
                payload = scene_channel.packed_id + packed_name
                packet = Packet(protocol=PacketProtocols.create_scene, payload=payload)
                queued_packets.append(packet)

                scene_channel.is_initial = False

            if deleted_data:
                deletion_payload = scene_channel.packed_id + b''.join(deleted_data)
                deletion_packet = Packet(PacketProtocols.delete_replicable, payload=deletion_payload, reliable=True)

                queued_packets.append(deletion_packet)

            if creation_data:
                creation_payload = scene_channel.packed_id + b''.join(creation_data)
                creation_packet = Packet(PacketProtocols.create_replicable, payload=creation_payload, reliable=True)
                queued_packets.append(creation_packet)

            if reliable_invoke_method_data:
                reliable_array = pack_variable_array(array_length_serialiser, reliable_invoke_method_data)
                reliable_method_payload = scene_channel.packed_id + reliable_array

                reliable_method_packet = Packet(PacketProtocols.invoke_method, payload=reliable_method_payload,
                                                reliable=True)
                queued_packets.append(reliable_method_packet)

            if unreliable_invoke_method_data:
                unreliable_array = pack_variable_array(array_length_serialiser, unreliable_invoke_method_data)
                unreliable_method_payload = scene_channel.packed_id + unreliable_array

                unreliable_method_packet = Packet(PacketProtocols.invoke_method, payload=unreliable_method_payload)
                queued_packets.append(unreliable_method_packet)

            if attribute_data:
                attribute_payload = scene_channel.packed_id + b''.join(attribute_data)
                attribute_packet = Packet(PacketProtocols.update_attributes, payload=attribute_payload)
                queued_packets.append(attribute_packet)

            # Force joined packet
            if creation_data or is_new_scene:
                collection = PacketCollection(queued_packets)
                queue_packet(collection)

            # Else normal queuing
            else:
                for packet in queued_packets:
                    queue_packet(packet)

        # Send scene deletions
        for scene_channel in self.deleted_channels:
            payload = scene_channel.packed_id
            deletion_packet = Packet(protocol=PacketProtocols.delete_scene, payload=payload)
            queue_packet.append(deletion_packet)

        self.deleted_channels.clear()


class ClientReplicationManager(ReplicationManagerBase):

    channel_class = ClientSceneChannel

    def __init__(self, world, connection):
        super().__init__(world, connection)

        self._string_handler = get_serialiser_for(str)
        self._bool_handler = get_serialiser_for(bool)

        self._pending_notifications = defaultdict(list)
        connection.post_receive_callbacks.append(self._dispatch_notifications)

    @on_protocol(PacketProtocols.create_scene)
    def on_create_scene(self, packet):
        scene_id, id_size = SceneChannelBase.id_handler.unpack_from(packet.payload)
        scene_name, name_size = self._string_handler.unpack_from(packet.payload, offset=id_size)

        # Create scene
        try:
            scene = self.world.scenes[scene_name]

        except KeyError:
            scene = self.world.add_scene(scene_name)

        self.scene_channels[scene_id] = ClientSceneChannel(self, scene, scene_id)

    @on_protocol(PacketProtocols.delete_scene)
    def on_delete_scene(self, packet):
        scene_id, id_size = SceneChannelBase.id_handler.unpack_from(packet.payload)

        scene_channel = self.scene_channels.pop(scene_id)
        scene = scene_channel.scene

        self.world.remove_scene(scene)

    @on_protocol(PacketProtocols.create_replicable)
    def on_create_replicable(self, packet):
        payload = packet.payload

        scene_id, offset = SceneChannelBase.id_handler.unpack_from(payload)

        scene_channel = self.scene_channels[scene_id]
        scene = scene_channel.scene

        while offset < len(payload):
            unique_id, id_size = ReplicableChannelBase.id_handler.unpack_id(payload, offset=offset)
            offset += id_size

            type_name, type_size = self._string_handler.unpack_from(payload, offset=offset)
            offset += type_size

            is_connection_host, bool_size = self._bool_handler.unpack_from(payload, offset=offset)
            offset += bool_size

            # Create replicable of same type
            replicable_cls = Replicable.subclasses[type_name]

            try:
                replicable = scene.add_replicable(replicable_cls, unique_id, from_replication=True)

            except ExplicitReplicableIdCollisionError:
                existing = scene.replicables[unique_id]
                # Is same class
                if existing.__class__ is replicable_cls:
                    self.logger.warn("Assuming matching ID and class of explicitly assigned replicable is a static replicable")
                    replicable = existing

                # Can't recover this state
                else:
                    raise RuntimeError("Another replicable is using an explicit ID '{} with a different class '{}"
                                       .format(unique_id, replicable_cls))

            # If replicable is parent (top owner)
            if is_connection_host:
                # Register as own replicable
                scene_channel.root_replicable = replicable

    @on_protocol(PacketProtocols.delete_replicable)
    def on_delete_replicable(self, packet):
        payload = packet.payload

        scene_id, offset = SceneChannelBase.id_handler.unpack_from(payload)

        scene_channel = self.scene_channels[scene_id]
        scene = scene_channel.scene

        replicable_id_handler = ReplicableChannelBase.id_handler
        with replicable_id_handler.current_scene_as(scene):
            while offset < len(payload):
                replicable, id_size = ReplicableChannelBase.id_handler.unpack_from(payload, offset)
                offset += id_size
                if replicable is None:
                    continue

                scene.remove_replicable(replicable)

    @on_protocol(PacketProtocols.update_attributes)
    def on_update_attributes(self, packet):
        payload = packet.payload
        scene_id, offset = SceneChannelBase.id_handler.unpack_from(payload)

        # Latency may cause this to fail TODO - add queue to handle RPC calls + init/del
        scene_channel = self.scene_channels[scene_id]
        scene = scene_channel.scene

        replicable_channels = scene_channel.replicable_channels
        replicable_id_handler = ReplicableChannelBase.id_handler

        with replicable_id_handler.current_scene_as(scene):
            while offset < len(payload):
                unique_id, id_size = replicable_id_handler.unpack_id(payload, offset)
                offset += id_size

                try:
                    replicable_channel = replicable_channels[unique_id]

                except KeyError:
                    self.logger.error("Couldn't find channel for '{}', dropped remaining data ({} bytes)"
                                      .format(unique_id, len(payload) - offset))
                    break

                notifier, read_bytes = replicable_channel.read_attributes(payload, offset)
                offset += read_bytes

                self._pending_notifications[scene].append(notifier)

    def _dispatch_notifications(self):
        for scene, notifications in self._pending_notifications.items():

            for notification in notifications:
                notification()

        self._pending_notifications.clear()

    def send(self, is_network_tick):
        array_length_serialiser = self._array_length_serialiser

        for scene_channel in self.scene_channels.values():
            # Reliable packets
            reliable_invoke_method_data = []

            # Unreliable packets
            unreliable_invoke_method_data = []

            root_replicable = scene_channel.root_replicable
            no_role = Roles.none

            for replicable_channel in scene_channel.prioritised_channels:
                replicable = replicable_channel.replicable

                # Check if remote role is permitted
                if replicable.roles.remote == no_role:
                    continue

                is_owner = replicable.root is root_replicable

                # Write RPC calls
                if is_owner:
                    reliable_rpc_calls, unreliable_rpc_calls = replicable_channel.dump_rpc_calls()

                    if reliable_rpc_calls:
                        reliable_invoke_method_data.append(replicable_channel.packed_id + reliable_rpc_calls)

                    if unreliable_rpc_calls:
                        unreliable_invoke_method_data.append(replicable_channel.packed_id + unreliable_rpc_calls)

            # Now send packets
            if reliable_invoke_method_data:
                reliable_array = pack_variable_array(array_length_serialiser, reliable_invoke_method_data)
                reliable_method_payload = scene_channel.packed_id + reliable_array

                reliable_method_packet = Packet(PacketProtocols.invoke_method, payload=reliable_method_payload,
                                                reliable=True)
                self.connection.queue_packet(reliable_method_packet)

            if unreliable_invoke_method_data:
                unreliable_array = pack_variable_array(array_length_serialiser, unreliable_invoke_method_data)
                unreliable_method_payload = scene_channel.packed_id + unreliable_array

                unreliable_method_packet = Packet(PacketProtocols.invoke_method, payload=unreliable_method_payload)
                self.connection.queue_packet(unreliable_method_packet)