from ...signals import SceneRegisteredSignal, SceneUnregisteredSignal
from ...streams.replication.channels import ServerSceneChannel, ClientSceneChannel, SceneChannelBase, ReplicableChannelBase
from ..helpers import on_protocol, register_protocol_listeners
from ...enums import PacketProtocols, Roles
from ...handlers import get_handler
from ...packet import Packet
from ...replicable import Replicable
from ...type_flag import TypeFlag
from ...scene import NetworkScene
from ...world_info import WorldInfo

from operator import attrgetter


priority_getter = attrgetter("replication_priority")


class ReplicationManagerBase:

    channel_class = None

    def __init__(self, connection):
        self.connection = connection

        self.scene_channels = {}

        self.root_replicable = None

        # Listen to packets from connection
        register_protocol_listeners(self, connection.dispatcher)

    @SceneRegisteredSignal.on_global
    def on_scene_registered(self, target):
        self.scene_channels[target.instance_id] = self.channel_class(self.connection, scene=target)

    @SceneUnregisteredSignal.on_global
    def on_scene_unregistered(self, target):
        self.scene_channels.pop(target.instance_id)

    def send(self, is_network_tick):
        raise NotImplementedError()


class ServerReplicationManager(ReplicationManagerBase):

    channel_class = ServerSceneChannel

    def __init__(self, connection):
        super().__init__(connection)

        self.root_replicable = WorldInfo.rules.post_initialise(self)

        self._string_handler = get_handler(TypeFlag(str))
        self._bool_handler = get_handler(TypeFlag(bool))

    def _initialise_channel(self, channel):
        #TODO support scene natively
        packed_name = self._string_handler.pack(channel.scene.name)
        payload = channel.packed_id + packed_name
        packet = Packet(protocol=PacketProtocols.create_scene, payload=payload)
        self.connection.queue_packet(packet)

    def _replicate_channel(self, scene_channel):
        pack_string = self._string_handler.pack
        pack_bool = self._bool_handler.pack

        # Reliable
        creation_data = []
        deletion_data = []

        # Reliable packets
        reliable_invoke_method_data = []

        # Unreliable packets
        unreliable_invoke_method_data = []
        attribute_data = []

        root_replicable = self.root_replicable
        is_relevant = WorldInfo.rules.is_relevant

        no_role = Roles.none
        # TODO move this
        for replicable_channel in sorted(scene_channel.replicable_channels.values(), reverse=True, key=priority_getter):
            replicable = replicable_channel.replicable

            # Check if remote role is permitted
            if replicable.roles.remote == no_role:
                continue

            is_and_relevant_to_owner = replicable.relevant_to_owner and replicable.uppermost == root_replicable

            # Write RPC calls
            if is_and_relevant_to_owner:
                reliable_rpc_calls, unreliable_rpc_calls = replicable_channel.dump_rpc_calls()

                if reliable_rpc_calls:
                    reliable_invoke_method_data.append(replicable_channel.packed_id + reliable_rpc_calls)

                if unreliable_rpc_calls:
                    unreliable_invoke_method_data.append(replicable_channel.packed_id + unreliable_rpc_calls)

            replicable = replicable_channel.replicable

            if replicable_channel.awaiting_replication or is_and_relevant_to_owner \
                    or is_relevant(root_replicable, replicable):
                # Channel just created
                if replicable_channel.is_initial:
                    packed_class = pack_string(replicable.__class__.type_name)
                    packed_is_host = pack_bool(replicable == root_replicable)

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
                replicable_channel.replicable_channels.pop(replicable)

        # Now send packets
        # TODO - if any creation packets (scene / replicable, send everything together! that way order preserved)
        if creation_data:
            creation_payload = scene_channel.packed_id + b''.join(creation_data)
            creation_packet = Packet(PacketProtocols.create_replicable, payload=creation_payload, reliable=True)
            self.connection.queue_packet(creation_packet)

        if reliable_invoke_method_data:
            reliable_method_payload = scene_channel.packed_id + b''.join(reliable_invoke_method_data)
            reliable_method_packet = Packet(PacketProtocols.invoke_method, payload=reliable_method_payload, reliable=True)
            self.connection.queue_packet(reliable_method_packet)

        if unreliable_invoke_method_data:
            unreliable_method_payload = scene_channel.packed_id + b''.join(unreliable_invoke_method_data)
            unreliable_method_packet = Packet(PacketProtocols.invoke_method, payload=unreliable_method_payload)
            self.connection.queue_packet(unreliable_method_packet)

        if attribute_data:
            attribute_payload = scene_channel.packed_id + b''.join(attribute_data)
            attribute_packet = Packet(PacketProtocols.update_attributes, payload=attribute_payload)
            self.connection.queue_packet(attribute_packet)

    def send(self, is_network_tick):
        for channel in self.scene_channels.values():
            if channel.is_initial:
                self._initialise_channel(channel)
                channel.is_initial = False

            self._replicate_channel(channel)


class ClientReplicationManager(ReplicationManagerBase):

    channel_class = ClientSceneChannel

    def __init__(self, connection):
        super().__init__(connection)

        self._string_handler = get_handler(TypeFlag(str))
        self._bool_handler = get_handler(TypeFlag(bool))

        self._pending_notifications = []
        connection.post_receive_callbacks.append(self._dispatch_notifications)

    @on_protocol(PacketProtocols.create_scene)
    def on_create_scene(self, packet):
        scene_id, id_size = SceneChannelBase.id_handler.unpack_from(packet.payload)
        scene_name, name_size = self._string_handler.unpack_from(packet.payload, offset=id_size)

        # Create scene
        scene = NetworkScene(scene_name, instance_id=scene_id)

    @on_protocol(PacketProtocols.delete_scene)
    def on_delete_scene(self, packet):
        scene_id, id_size = SceneChannelBase.id_handler.unpack_from(packet.payload)
        scene = NetworkScene[scene_id]
        scene.deregister()

    @on_protocol(PacketProtocols.create_replicable)
    def on_create_replicable(self, packet):
        payload = packet.payload

        scene_id, offset = SceneChannelBase.id_handler.unpack_from(payload)
        scene = NetworkScene[scene_id]

        with scene.context:
            while offset < len(packet):
                instance_id, id_size = ReplicableChannelBase.id_handler.unpack_id(payload)
                offset += id_size

                type_name, type_size = self._string_handler.unpack_from(payload, offset=offset)
                offset += type_size

                is_connection_host, _ = self._bool_handler.unpack_from(payload, offset=offset)

                # Find replicable class
                replicable_cls = Replicable.from_type_name(type_name)

                # Create replicable of same type
                replicable = replicable_cls.create_or_return(instance_id)

                # If replicable is parent (top owner)
                if is_connection_host:
                    # Register as own replicable
                    self.root_replicable = replicable

    @on_protocol(PacketProtocols.delete_replicable)
    def on_delete_replicable(self, packet):
        raise NotImplementedError()

    @on_protocol(PacketProtocols.update_attributes)
    def on_update_attributes(self, packet):
        payload = packet.payload

        scene_id, offset = SceneChannelBase.id_handler.unpack_from(payload)
        scene = NetworkScene[scene_id]

        scene_channel = self.scene_channels[scene_id]
        replicable_channels = scene_channel.replicable_channels

        with scene.context:
            while offset < len(packet):
                instance_id, id_size = ReplicableChannelBase.id_handler.unpack_id(payload, offset)
                offset += id_size

                replicable_channel = replicable_channels[instance_id]
                notifier, read_bytes = replicable_channel.read_attributes(payload, offset)
                offset += read_bytes

                self._pending_notifications.extend(notifier)

    def _dispatch_notifications(self):
        for notification in self._pending_notifications:
            notification()

        self._pending_notifications.clear()

    def _replicate_channel(self, scene_channel):
        # Reliable packets
        reliable_invoke_method_data = []

        # Unreliable packets
        unreliable_invoke_method_data = []

        root_replicable = self.root_replicable
        no_role = Roles.none

        # TODO move this
        for replicable_channel in sorted(scene_channel.replicable_channels.values(), reverse=True, key=priority_getter):
            replicable = replicable_channel.replicable

            # Check if remote role is permitted
            if replicable.roles.remote == no_role:
                continue

            is_and_relevant_to_owner = replicable.relevant_to_owner and replicable.uppermost == root_replicable
            # Write RPC calls
            if is_and_relevant_to_owner:
                reliable_rpc_calls, unreliable_rpc_calls = replicable_channel.dump_rpc_calls()

                if reliable_rpc_calls:
                    reliable_invoke_method_data.append(replicable_channel.packed_id + reliable_rpc_calls)

                if unreliable_rpc_calls:
                    unreliable_invoke_method_data.append(replicable_channel.packed_id + unreliable_rpc_calls)

        # Now send packets
        if reliable_invoke_method_data:
            reliable_method_payload = scene_channel.packed_id + b''.join(reliable_invoke_method_data)
            reliable_method_packet = Packet(PacketProtocols.invoke_method, payload=reliable_method_payload,
                                            reliable=True)
            self.connection.queue_packet(reliable_method_packet)

        if unreliable_invoke_method_data:
            unreliable_method_payload = scene_channel.packed_id + b''.join(unreliable_invoke_method_data)
            unreliable_method_packet = Packet(PacketProtocols.invoke_method, payload=unreliable_method_payload)
            self.connection.queue_packet(unreliable_method_packet)

    def send(self, is_network_tick):
        for channel in self.scene_channels.values():
            self._replicate_channel(channel)