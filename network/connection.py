from .packet import Packet
from .handler_interfaces import get_handler
from .descriptors import StaticValue
from .replicables import Replicable, WorldInfo
from .signals import ReplicableUnregisteredSignal, ReplicableRegisteredSignal, SignalListener
from .enums import Roles, Protocols
from .channel import ClientChannel, ServerChannel


def respect_bandwidth(func):
    def wrapper(*args, bandwidth, **kwargs):
        bandwidth_used = 0
        generator = func(*args, **kwargs)

        try:
            while bandwidth > bandwidth_used:
                packet = next(generator)
                bandwidth_used += packet.size
                yield packet

        except StopIteration:
            return
    return wrapper


class Connection(SignalListener):

    channel_class = None

    def __init__(self, netmode):
        self.netmode = netmode
        self.replicable = None

        self.channels = {}

        self.string_packer = get_handler(StaticValue(str))
        self.int_packer = get_handler(StaticValue(int))
        self.replicable_packer = get_handler(StaticValue(Replicable))

        self.register_signals()

    @ReplicableUnregisteredSignal.global_listener
    def notify_unregistration(self, target):
        self.channels.pop(target.instance_id)

    @ReplicableRegisteredSignal.global_listener
    def notify_registration(self, target):
        '''Create channel for context with network id
        @param instance_id: network id of context'''
        self.channels[target.instance_id] = self.channel_class(self, target)

    def on_delete(self):
        self.replicable.request_unregistration()

    def is_owner(self, replicable):
        '''Determines if a connection owns this replicable
        Searches for Replicable with same network id as our Controller'''
        # Determine if parent is our controller
        parent = replicable.uppermost
        try:
            return parent.instance_id == \
                self.replicable.instance_id

        except AttributeError:
            return False

    @staticmethod
    def get_replication_priority(entry):
        replicable, (is_owner, channel) = entry
        return replicable.replication_priority

    @property
    def relevant_replicables(self):
        check_is_owner = self.is_owner
        channels = self.channels
        no_role = Roles.none

        for replicable in Replicable:
            # Check if remote role is permitted
            if replicable.roles.remote == no_role:
                continue

            channel = channels[replicable.instance_id]

            # Now check if we are an owner, or relevant
            is_owner = check_is_owner(replicable)
            if (is_owner and not replicable.irrelevant_to_owner):
                yield replicable, (is_owner, channel)

    def get_method_replication(self):
        channels = self.channels
        method_invoke = Protocols.method_invoke
        make_packet = Packet

        for (replicable, (is_owner, channel)) in self.relevant_replicables:
            # Get network ID
            instance_id = replicable.instance_id

            # Get attribute channel
            channel = channels[instance_id]

            # Send RPC calls if we are the owner
            if channel.has_rpc_calls and is_owner:
                packed_id = channel.packed_id

                for rpc_call, reliable in channel.take_rpc_calls():
                    rpc_data = packed_id + rpc_call

                    yield make_packet(protocol=method_invoke,
                                      payload=rpc_data,
                                      reliable=reliable)


class ClientConnection(Connection):

    channel_class = ClientChannel

    def set_replication(self, packet):
        '''Replication function
        Accepts replication packets and responds to protocol
        @param packet: replication packet'''

        instance_id = self.replicable_packer.unpack_id(packet.payload)

        # If an update for a replicable
        if packet.protocol == Protocols.replication_update:

            if Replicable.graph_has_instance(instance_id):
                channel = self.channels[instance_id]
                channel.set_attributes(packet.payload[
                                      self.replicable_packer.size():])

            else:
                print("Unable to replicate to replicable with id {}"
                      .format(instance_id))

        # If it is an RPC call
        elif packet.protocol == Protocols.method_invoke:

            if Replicable.graph_has_instance(instance_id):
                channel = self.channels[instance_id]

                if self.is_owner(channel.replicable):
                    channel.invoke_rpc_call(packet.payload[
                                           self.replicable_packer.size():])

        # If construction for replicable
        elif packet.protocol == Protocols.replication_init:

            id_size = self.replicable_packer.size()

            type_name = self.string_packer.unpack_from(
                       packet.payload[id_size:])

            type_size = self.string_packer.size(
                        packet.payload[id_size:])

            is_connection_host = bool(self.int_packer.unpack_from(
                       packet.payload[id_size + type_size:]))

            # Create replicable of same type
            replicable_cls = Replicable.from_type_name(type_name)
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
        elif packet.protocol == Protocols.replication_del:

            # If the replicable exists
            try:
                replicable = Replicable.get_from_graph(instance_id)

            except LookupError:
                pass

            else:
                replicable.request_unregistration()

    def send(self, network_tick, available_bandwidth):
        '''Client connection send method
        Sends data using initialised context
        Sends RPC information
        Generator'''
        yield from self.get_method_replication()

    def receive(self, packets):
        '''Client connection receive method
        Receive data using initialised context
        Receive RPC and replication information
        Catches network errors'''
        for packet in packets:
            protocol = packet.protocol

            if protocol in Protocols:
                self.set_replication(packet)


class ServerConnection(Connection):

    channel_class = ServerChannel

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
        @param replicable: replicable that died'''
        # Send delete packet
        channel = self.channels[target.instance_id]
        self.cached_packets.add(Packet(protocol=Protocols.replication_del,
                                    payload=channel.packed_id, reliable=True))

        super().notify_unregistration(target)

    @staticmethod
    def get_replication_priority(entry):
        replicable, (is_owner, channel) = entry
        try:
            interval = (WorldInfo.elapsed - channel.last_replication_time)

        except TypeError:
            return replicable.replication_priority

        elapsed_fraction = (interval / replicable.replication_update_period)
        return replicable.replication_priority + (elapsed_fraction - 1)

    @property
    def prioritised_replicables(self):
        return sorted(self.relevant_replicables, reverse=True,
                      key=self.get_replication_priority)

    @property
    def relevant_replicables(self):
        is_relevant = WorldInfo.rules.is_relevant
        connection_replicable = self.replicable

        check_is_owner = self.is_owner
        channels = self.channels
        no_role = Roles.none

        for replicable in Replicable:
            # Check if remote role is permitted
            if replicable.roles.remote == no_role:
                continue

            channel = channels[replicable.instance_id]

            # Now check if we are an owner, or relevant
            is_owner = check_is_owner(replicable)
            if ((is_owner and not replicable.irrelevant_to_owner) or
                is_relevant(connection_replicable, replicable)):
                yield replicable, (is_owner, channel)

    @respect_bandwidth
    def get_attribute_replication(self):
        '''Yields replication packets for relevant replicable
        @param replicable: replicable to replicate'''
        channels = self.channels

        make_packet = Packet
        cached_packets = self.cached_packets
        cache_packet = cached_packets.add
        uncache_packet = cached_packets.pop

        method_invoke = Protocols.method_invoke
        replication_init = Protocols.replication_init
        replication_update = Protocols.replication_update

        timestamp = WorldInfo.elapsed

        for (replicable, (is_owner, channel)) in self.prioritised_replicables:
            # Get network ID
            instance_id = replicable.instance_id
            # Get attribute channel
            channel = channels[instance_id]
            packed_id = channel.packed_id

            # Check whether enough time has elapsed
            try:
                interval = (timestamp - channel.last_replication_time)

            except TypeError:
                pass

            else:
                if interval < replicable.replication_update_period:
                    continue

            # Only send attributes if relevant
            # player controller and replicable
            # If we've never replicated to this channel
            if channel.last_replication_time is None:
                # Pack the class name
                packed_class = self.string_packer.pack(
                                   replicable.__class__.type_name)
                packed_is_host = self.int_packer.pack(
                                  replicable == self.replicable)
                # Send the protocol, class name and owner status to client
                def T(p):
                    print("YES")
                def F(p):
                    print("NO")
                yield make_packet(protocol=replication_init,
                                  payload=packed_id + packed_class +\
                                  packed_is_host, reliable=True, on_success=T,
                                  on_failure=F)

            # Send changed attributes
            attributes = channel.get_attributes(is_owner, timestamp)

            # If they have changed
            if attributes:
                # This ensures references exist
                # By calling it after all creation packets are yielded
                update_payload = packed_id + attributes
                cache_packet(make_packet(
                                        protocol=replication_update,
                                        payload=update_payload,
                                        reliable=True))

        # Send any additional data
        while cached_packets:
            yield uncache_packet()

    def receive(self, packets):
        '''Server connection receive method
        Receive data using initialised context
        Receive RPC information'''
        # Local space variables
        is_owner = self.is_owner
        channels = self.channels

        unpacker = self.replicable_packer.unpack_id
        id_size = self.replicable_packer.size()

        method_invoke = Protocols.method_invoke

        # Run RPC invoke for each packet
        for packet in packets:
            # If it is an RPC packet
            if packet.protocol == method_invoke:
                # Unpack data
                instance_id = unpacker(packet.payload)
                channel = channels[instance_id]

                # If we have permission to execute
                if is_owner(channel.replicable):
                    channel.invoke_rpc_call(packet.payload[id_size:])

    def send(self, network_tick, available_bandwith):
        '''Server connection send method
        Sends data using initialised context
        Sends RPC and replication information
        Generator
        @param network_tick: send any non urgent data (& RPC)
        @param available_bandwidth: number of bytes predicted to be available'''

        yield from self.get_method_replication()

        if network_tick:
            yield from self.get_attribute_replication(
                                             bandwidth=available_bandwith)

