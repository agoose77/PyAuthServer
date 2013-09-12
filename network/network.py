from .actors import BaseWorldInfo, Replicable, WorldInfo
from .argument_serialiser import ArgumentSerialiser
from .bitfield import Bitfield
from .descriptors import StaticValue
from .enums import Netmodes, Roles, Protocols, ConnectionStatus
from .errors import NetworkError, TimeoutError
from .handler_interfaces import (register_handler,
                                 get_handler, register_description)
from .modifiers import reliable
from .registers import InstanceRegister, InstanceNotifier, TypeRegister
from .packet import Packet, PacketCollection
from .channel import ClientChannel, ServerChannel

from collections import deque
from functools import wraps
from operator import eq as equals_operator
from socket import (socket, AF_INET, SOCK_DGRAM,
                    error as socket_error, gethostbyname)
from time import monotonic
from weakref import proxy as weak_proxy


class run_only_on:
    '''Runs method in netmode specific scope only'''

    def __init__(self, netmode):
        self.netmode = netmode

    def __call__(self, func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if WorldInfo.netmode != self.netmode:
                return
            return func(*args, **kwargs)
        return wrapper


class Connection(InstanceNotifier):

    channel_class = None

    def __init__(self, netmode):
        super().__init__()

        self.netmode = netmode
        self.channels = {}

        self.replicable = None

        self.string_packer = get_handler(StaticValue(str))
        self.int_packer = get_handler(StaticValue(int))
        self.replicable_packer = get_handler(StaticValue(Replicable))

        Replicable.subscribe(self)  # @UndefinedVariable

    def notify_unregistration(self, replicable):
        self.channels.pop(replicable.instance_id)

    def notify_registration(self, replicable):
        '''Create channel for replicable with network id
        @param instance_id: network id of replicable'''
        proxy = weak_proxy(replicable)
        channel = self.channel_class(self, proxy)
        self.channels[replicable.instance_id] = channel

    def on_delete(self):
        pass

    def is_owner(self, replicable):
        '''Determines if a connection owns this replicable
        Searches for Replicable with same network id as our Controller'''
        last = None

        # Walk the parent tree until no parent
        while replicable:
            owner = getattr(replicable, "owner", None)
            last, replicable = replicable, owner

        # Determine if parent is our controller
        try:
            return last.instance_id == self.replicable.instance_id

        except AttributeError:
            return False

    def get_method_replication(self):

        check_is_owner = self.is_owner
        get_channel = self.channels.__getitem__
        packer = self.replicable_packer.pack_id
        no_role = Roles.none
        method_invoke = Protocols.method_invoke

        for replicable in Replicable:

            if replicable.roles.remote == no_role:
                continue

            # Get network ID
            instance_id = replicable.instance_id
            packed_id = packer(instance_id)

            # Get attribute channel
            channel = get_channel(instance_id)

            # Send RPC calls if we are the owner
            if channel.has_rpc_calls and check_is_owner(replicable):
                for rpc_call, reliable in channel.take_rpc_calls():
                    rpc_data = packed_id + rpc_call

                    yield Packet(protocol=method_invoke,
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
                channel.set_attributes(packet.payload[1:])

            else:
                print("Unable to replicate to replicable with id {}"
                      .format(instance_id))

        # If it is an RPC call
        elif packet.protocol == Protocols.method_invoke:

            if Replicable.graph_has_instance(instance_id):
                channel = self.channels[instance_id]

                if self.is_owner(channel.replicable):
                    channel.invoke_rpc_call(packet.payload[1:])

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
            # If replicable is Controller
            if is_connection_host:

                # Register as own replicable
                self.replicable = weak_proxy(replicable)

        # If it is the deletion request
        elif packet.protocol == Protocols.replication_del:

            # If the replicable exists
            try:
                replicable = Replicable.get_from_graph(instance_id)

            except LookupError:
                pass

            else:
                replicable.request_unregistration()

    def send(self, network_tick):
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

            if protocol == Protocols.replication_update:
                self.set_replication(packet)

            elif protocol == Protocols.method_invoke:
                self.set_replication(packet)

            elif protocol == Protocols.replication_init:
                self.set_replication(packet)

            elif protocol == Protocols.replication_del:
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

    def notify_unregistration(self, replicable):
        '''Called when replicable dies
        @param replicable: replicable that died'''
        super().notify_unregistration(replicable)

        instance_id = replicable.instance_id
        packed_id = self.replicable_packer.pack_id(instance_id)

        # Send delete packet
        self.cached_packets.add(Packet(protocol=Protocols.replication_del,
                                    payload=packed_id, reliable=True))

    def get_full_replication(self):
        '''Yields replication packets for relevant replicable
        @param replicable: replicable to replicate'''
        is_relevant = WorldInfo.game_info.is_relevant
        id_packer = self.replicable_packer.pack_id
        check_is_owner = self.is_owner
        get_channel = self.channels.__getitem__

        no_role = Roles.none

        method_invoke = Protocols.method_invoke
        replication_init = Protocols.replication_init
        replication_update = Protocols.replication_update

        for replicable in Replicable:
            # We cannot network remote roles of None
            if replicable.roles.remote == no_role:
                continue

            # Determine if we own this replicable
            is_owner = check_is_owner(replicable)

            # Get network ID
            instance_id = replicable.instance_id
            packed_id = id_packer(instance_id)

            # Get attribute channel
            channel = get_channel(instance_id)

            # Send RPC calls if we are the owner
            if channel.has_rpc_calls and is_owner:
                for rpc_call, reliable in channel.take_rpc_calls():
                    yield Packet(protocol=method_invoke,
                                      payload=packed_id + rpc_call,
                                      reliable=reliable)

            # Only send attributes if relevant
            # player controller and replicable
            if is_owner or is_relevant(self.replicable, replicable):
                # If we've never replicated to this channel
                if channel.is_initial:
                    # Pack the class name
                    packed_class = self.string_packer.pack(
                                       replicable.__class__.type_name)
                    packed_is_host = self.int_packer.pack(
                                      replicable == self.replicable)
                    # Send the protocol, class name and owner status to client
                    yield Packet(protocol=replication_init,
                                      payload=packed_id + packed_class +\
                                      packed_is_host, reliable=True)

                # Send changed attributes
                attributes = channel.get_attributes(is_owner)

                # If they have changed
                if attributes:
                    # This ensures references exist
                    # By calling it after all creation packets are yielded
                    update_payload = packed_id + attributes
                    self.cached_packets.add(Packet(
                                            protocol=replication_update,
                                            payload=update_payload,
                                            reliable=True))

        # Send any additional data
        if self.cached_packets:
            yield from self.cached_packets
            self.cached_packets.clear()

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

    def send(self, network_tick):
        '''Server connection send method
        Sends data using initialised context
        Sends RPC and replication information
        Generator
        @param network_tick: send any non urgent data (& RPC)'''

        if network_tick:
            yield from self.get_full_replication()
        else:
            yield from self.get_method_replication()


class ConnectionInterface(metaclass=InstanceRegister):

    def __init__(self, addr, on_error=None,
                 on_timeout=None, on_connected=None):
        self.on_error = on_error
        self.on_timeout = on_timeout
        self.on_connected = on_connected

        # Maximum sequence number value
        self.sequence_max_size = 255 ** 2
        self.sequence_handler = get_handler(StaticValue(int,
                                            max_value=self.sequence_max_size))

        # Number of packets to ack per packet
        self.ack_window = 32

        # Bitfield and bitfield size
        self.ack_bitfield = Bitfield(self.ack_window)
        self.ack_packer = get_handler(StaticValue(Bitfield))

        # Additional data
        self.netmode_packer = get_handler(StaticValue(int))
        self.error_packer = get_handler(StaticValue(str))

        # Protocol unpacker
        self.protocol_handler = get_handler(StaticValue(int))

        # Storage for packets requesting ack or received
        self.requested_ack = {}
        self.received_window = deque()

        # Current indicators of latest out/incoming sequence numbers
        self.local_sequence = 0
        self.remote_sequence = 0

        # Time out for connection before it is deleted
        self.time_out = 2
        self.last_received = monotonic()

        # Simple connected status
        self.status = ConnectionStatus.disconnected

        # Maintains an actual connection
        self.connection = None

        self.buffer = []

        # Maintenance info
        self._addr = self.convert_address(addr)

        if self._addr is not None:
            super().__init__(instance_id=self._addr, register=True)

    def __new__(cls, *args, **kwargs):
        """Constructor switch depending upon netmode"""
        if cls is ConnectionInterface:
            netmode = WorldInfo.netmode

            if netmode == Netmodes.server:
                return ServerInterface.__new__(ServerInterface,
                                               *args, **kwargs)

            elif netmode == Netmodes.client:
                return ClientInterface.__new__(ClientInterface,
                                               *args, **kwargs)
        else:
            return super().__new__(cls)

    def on_unregistered(self):
        super().on_unregistered()

        if self.connection:
            self.connection.on_delete()

    def convert_address(self, addr):
        '''Unifies alias address names
        @param addr: address to clean'''
        try:
            return gethostbyname(addr[0]), addr[1]
        except Exception as err:
            if callable(self.on_error):
                self.on_error(err)
            else:
                raise

    @classmethod
    def by_status(cls, status, comparator=equals_operator):
        count = 0
        for interface in cls:
            if comparator(interface.status, status):
                count += 1
        return count

    @property
    def next_local_sequence(self):
        current_sequence = self.local_sequence
        self.local_sequence = (current_sequence + 1) if (current_sequence <
                                             self.sequence_max_size) else 0
        return self.local_sequence

    def set_time_out(self, delay):
        self.time_out = delay

    def sequence_more_recent(self, s1, s2):
        half_seq = (self.sequence_max_size / 2)
        return ((s1 > s2) and (s1 - s2) <= half_seq) or ((s2 > s1)
                                             and (s2 - s1) > half_seq)

    def delete(self):
        self.status = ConnectionStatus.deleted

    def connected(self, *args, **kwargs):
        self.status = ConnectionStatus.connected

        if callable(self.on_connected):
            self.on_connected()

    def send(self, network_tick):

        # Check for timeout
        if (monotonic() - self.last_received) > self.time_out:
            self.status = ConnectionStatus.timeout

            err = TimeoutError("Connection to {} timed out".format(self._addr))

            if callable(self.on_timeout):
                self.on_timeout(err)
            else:
                raise err

        # If not connected setup handshake
        if self.status == ConnectionStatus.disconnected:
            packets = self.get_handshake()
            self.status = ConnectionStatus.handshake

        # If connected send normal data
        elif self.status == ConnectionStatus.connected:
            packets = self.connection.send(network_tick)

        # Don't send any data between states
        else:
            return

        # Create a packet collection from data
        packet_collection = PacketCollection(packets)

        # Include any re-send
        if self.buffer:
            # Read buffer
            packet_collection += PacketCollection(self.buffer)
            # Empty buffer
            self.buffer.clear()

        # Create a bitfield using window config
        ack_bitfield = self.ack_bitfield

        # The last received sequence number and received list
        remote_sequence = self.remote_sequence
        received_window = self.received_window

        # Acknowledge all packets we've received
        for index in range(self.ack_window):
            packet_sqn = remote_sequence - (index + 1)

            if packet_sqn < 0:
                continue

            ack_bitfield[index] = packet_sqn in received_window

        # Self-incrementing sequence property
        sequence = self.next_local_sequence

        # Construct header information
        ack_info = [self.sequence_handler.pack(sequence),
                    self.sequence_handler.pack(remote_sequence),
                    self.ack_packer.pack(ack_bitfield)]

        # Store acknowledge request for reliable members of packet
        self.requested_ack[sequence] = packet_collection

        # Add user data after header
        packet_bytes = packet_collection.to_bytes()

        if packet_bytes:
            ack_info.append(packet_bytes)

        # Return as bytes
        return b''.join(ack_info)

    def receive(self, bytes_):
        # Get the sequence id
        sequence = self.sequence_handler.unpack_from(bytes_)
        bytes_ = bytes_[self.sequence_handler.size():]

        # Get the base value for the bitfield
        ack_base = self.sequence_handler.unpack_from(bytes_)
        bytes_ = bytes_[self.sequence_handler.size():]

        # Read the acknowledgement bitfield
        self.ack_packer.unpack_merge(self.ack_bitfield, bytes_)
        bytes_ = bytes_[self.ack_packer.size(bytes_):]

        # Recreate packet collection
        packet_collection = PacketCollection().from_bytes(bytes_)

        # Store the received time
        self.last_received = monotonic()

        # If we receive a newer foreign sequence, update our local record
        if self.sequence_more_recent(sequence, self.remote_sequence):
            self.remote_sequence = sequence

        # Add packet to received list
        self.received_window.append(sequence)

        # Limit received size
        if len(self.received_window) > self.ack_window:
            self.received_window.popleft()

        # Dictionary of packets waiting for acknowledgement
        requested_ack = self.requested_ack
        ack_bitfield = self.ack_bitfield

        # Iterate over ACK bitfield
        for index in range(self.ack_window):
            sequence = ack_base - (index + 1)

            # If it was acked successfully
            flag = ack_bitfield[index]

            # If we are waiting for this packet, acknowledge it
            if (flag and sequence in requested_ack):
                requested_ack.pop(sequence).on_ack()

        # Acknowledge the sequence of this packet about
        if ack_base in self.requested_ack:
            requested_ack.pop(ack_base).on_ack()

        # If the packet drops off the ack_window assume it is lost
        likely_dropped = [k for k in requested_ack.keys()
                          if (sequence - k) > self.ack_window]

        # Find packets we think are dropped and resend them
        for sequence in likely_dropped:
            # Only reliable members asked to be informed if received/dropped
            reliable_collection = requested_ack.pop(sequence).to_reliable()
            reliable_collection.on_not_ack()
            self.buffer.append(reliable_collection)

        # Called for handshake protocol
        receive_handshake = self.receive_handshake

        # Call post-processed receive
        if self.status != ConnectionStatus.connected:
            for member in packet_collection.members:

                if member.protocol > Protocols.request_auth:
                    continue

                receive_handshake(member)

        else:
            self.connection.receive(packet_collection.members)


class ServerInterface(ConnectionInterface):

    def __init__(self, addr):
        super().__init__(addr)

        self._auth_error = None

    def get_handshake(self):
        '''Will only exist if invoked'''
        connection_failed = self.connection is None

        if connection_failed:

            if self._auth_error:
                # Send the error code
                err_name = self.error_packer.pack(
                                          type(self.auth_error).type_name)
                err_body = self.error_packer.pack(
                                          self._auth_error.args[0])

                # Yield a reliable packet
                return Packet(protocol=Protocols.auth_failure,
                              payload=err_name + err_body,
                              on_success=self.delete)

        else:
            # Send acknowledgement
            return Packet(protocol=Protocols.auth_success,
                          payload=self.netmode_packer.pack(WorldInfo.netmode),
                          on_success=self.connected)

    def receive_handshake(self, packet):
        # Unpack data
        netmode = self.netmode_packer.unpack_from(packet.payload)

        # Store replicable
        try:
            WorldInfo.game_info.pre_initialise(self.instance_id, netmode)

        # If a NetworkError is raised store the result
        except NetworkError as err:
            self._auth_error = err

        else:
            self.connection = ServerConnection(netmode)
            returned_replicable = WorldInfo.game_info.post_initialise(
                                                          self.connection)
            # Replicable is boolean false until registered
            # User can force register though!
            if returned_replicable is not None:
                self.connection.replicable = weak_proxy(returned_replicable)


class ClientInterface(ConnectionInterface):

    def get_handshake(self):
        return Packet(protocol=Protocols.request_auth,
                      payload=self.netmode_packer.pack(WorldInfo.netmode),
                      reliable=True)

    def receive_handshake(self, packet):
        protocol = packet.protocol

        if protocol == Protocols.auth_failure:
            err_data = packet.payload[self.error_packer.size(packet.payload):]
            err_type = self.error_packer.unpack_from(packet.payload)
            err_body = self.error_packer.unpack_from(err_data)
            err = NetworkError.from_type_name(err_type)

            if callable(self.on_error):
                self.on_error(err)
            else:
                raise err

        # Get remote network mode
        netmode = self.netmode_packer.unpack_from(packet.payload)
        # Must be success
        self.connection = ClientConnection(netmode)
        self.connected()


class Network(socket):

    def __init__(self, addr, port, update_interval=1 / 20):
        '''Network socket initialiser'''
        super().__init__(AF_INET, SOCK_DGRAM)

        self.bind((addr, port))
        self.setblocking(False)

        self._interval = update_interval
        self._last_sent = 0.0
        self._started = monotonic()

        self.sent_bytes = 0
        self.received_bytes = 0

    @property
    def can_send(self):
        '''Determines if the socket can send
        Result according to time elapsed >= send interval'''
        return (monotonic() - self._last_sent) >= self._interval

    @property
    def send_rate(self):
        return (self.sent_bytes / (monotonic() - self._started))

    @property
    def receive_rate(self):
        return (self.received_bytes / (monotonic() - self._started))

    def stop(self):
        self.close()

    def sendto(self, *args, **kwargs):
        '''Overrides sendto method to record sent time'''
        result = super().sendto(*args, **kwargs)

        self.sent_bytes += result
        return result

    def recvfrom(self, buff_size=63553):
        '''A partial function for recvfrom
        Used in iter(func, sentinel)'''
        try:
            return super().recvfrom(buff_size)
        except socket_error:
            return

    def receive(self):
        '''Receive all data from socket'''
        # Get connections
        get_connection = ConnectionInterface.get_from_graph

        # Receives all incoming data
        for bytes_, addr in iter(self.recvfrom, None):
            # Find existing connection for address
            try:
                connection = get_connection(addr)

            # Create a new interface to handle connection
            except LookupError:
                connection = ConnectionInterface(addr)

            # Dispatch data to connection
            connection.receive(bytes_)
            self.received_bytes += len(bytes_)

        # Apply any changes to the Connection interface
        ConnectionInterface.update_graph()

    def send(self):
        '''Send all connection data and update timeouts'''
        # A switch between emergency and normal
        network_tick = self.can_send

        # Get connections
        to_delete = []

        send_func = self.sendto

        # Send all queued data
        for connection in ConnectionInterface:

            # If the connection should be removed (timeout or explicit)
            if connection.status < ConnectionStatus.disconnected:
                connection.request_unregistration()
                continue

            # Give the option to send nothing
            data = connection.send(network_tick)

            # If returns data, send it
            if data:
                send_func(data, connection.instance_id)

        if network_tick:
            self._last_sent = monotonic()

        # Delete dead connections
        ConnectionInterface.update_graph()

    def connect_to(self, conn, *args, **kwargs):
        return ConnectionInterface(conn, *args, **kwargs)


class TypeHandler:

    def __init__(self, static_value):
        self.base_type = static_value.data['pointer_type']
        self.string_packer = get_handler(StaticValue(str))

    def pack(self, cls):
        return self.string_packer.pack(cls.type_name)

    def unpack(self, bytes_):
        name = self.string_packer.unpack_from(bytes_)
        cls = self.base_type.from_type_name(name)
        return cls

    def size(self, bytes_=None):
        return self.string_packer.size(bytes_)

    unpack_from = unpack


def type_description(cls):
    return hash(cls.type_name)


class RolesHandler:
    packer = get_handler(StaticValue(int))

    @classmethod
    def pack(cls, roles):
        with roles.switched():
            return cls.packer.pack(roles.local) + cls.packer.pack(roles.remote)

    @classmethod
    def unpack(cls, bytes_):
        return Roles(cls.packer.unpack(bytes_), cls.packer.unpack(bytes_[1:]))

    @classmethod
    def size(cls, bytes_=None):
        return 2 * cls.packer.size()

    unpack_from = unpack


register_handler(TypeRegister, TypeHandler, True)
register_handler(Roles, RolesHandler)
register_description(TypeRegister, type_description)
