from .serialiser import UInt8, UInt16, UInt32, UInt64, Float8, Float4, String
from .modifiers import reliable, simulated, is_reliable, is_simulated
from .bases import TypeRegister, StaticValue, Attribute
from .enums import Netmodes, Roles, Protocols, ConnectionStatus
from .actors import BaseWorldInfo, Controller, Replicable
from .handler_interfaces import static_description, register_handler, get_handler, smallest_int_handler

from bitarray import bitarray, bits2bytes

from socket import socket, AF_INET, SOCK_DGRAM, error as socket_error
from collections import deque, defaultdict, OrderedDict
from inspect import getmembers, signature
from itertools import repeat, chain
from copy import deepcopy, copy
from random import choice
from time import time

import operator

class NetworkError(Exception, metaclass=TypeRegister):
    _types = {}
    
class keyeddefaultdict(defaultdict):
    '''Dictionary with factory for missing keys
    Provides key to factory function provided to initialiser'''
    def __missing__(self, key):
        self[key] = value = self.default_factory(key)
        return value

class Serialiser:
    def __init__(self, arguments):
        '''Accepts ordered dict as argument'''        
        self.bools = [(name, value) for name, value in arguments.items() if value._type is bool]
        self.others = [(name, value) for name, value in arguments.items() if value._type is not bool]
        self.handlers = [(name, get_handler(value)) for name, value in self.others]
        
        self.total_normal = len(self.others)
        self.total_bools = len(self.bools)
        self.total_contents = self.total_normal + bool(self.total_bools)
        
        # Bitfields used for packing (so now bool packing expects cache)
        self.content_bits = bitarray(False for i in range(self.total_contents))
        self.bool_bits = bitarray(False for i in range(self.total_bools))
        
        self.bool_size = bits2bytes(self.total_bools)
        self.content_size = bits2bytes(self.total_normal)
        
    def unpack(self, bytes_, previous_values={}):
        '''Accepts ordered bytes, and optional previous values'''
        contents = bitarray(); contents.frombytes(bytes_[:self.content_size])
        bytes_ = bytes_[self.content_size:]
        
        for included, (key, handler) in zip(contents, self.handlers):
            if not included:
                continue
            
            if hasattr(handler, "unpack_merge"):
                value = previous_values[key]
                
                if value is None:
                    value = handler.unpack_from(bytes_)
                else:
                    handler.unpack_merge(value, bytes_)
            else:
                value = handler.unpack_from(bytes_)
                
            yield (key, value)
            
            bytes_ = bytes_[handler.size(bytes_):]
        
        if self.bools and contents[self.total_contents - 1]:
            bools = bitarray(); bools.frombytes(bytes_[:self.bool_size])
            bytes_ = bytes_[self.bool_size:]
            
            for value, (key, static_value) in zip(bools, self.bools):
                yield (key, value)

    def pack(self, data):
        # Reset content mask
        contents = self.content_bits
        contents.setall(False)
        
        # Create output list
        output = []
        
        # Iterate over non booleans
        for index, (key, handler) in enumerate(self.handlers):
            if not key in data:
                continue
            
            contents[index] = True
            output.append(handler.pack(data.pop(key)))
        
        # If we have boolean values remaining
        if data:
            # Reset bool mask
            bools = self.bool_bits
            bools.setall(False)
            
            # Iterate over booleans
            for index, (key, static) in enumerate(self.bools):
                if not key in data:
                    continue
                
                bools[index] = data[key]
                
            contents[-1] = True
            output.append(bools.tobytes())
      
        return contents.tobytes() + b''.join(output)
           
class RPC:
    """Mediates RPC calls to/from peers"""
    __annotations__ = {}
    _instances = {}
    
    def __init__(self, func, inst=None):
            
        if inst is None:
            self.func = func
            self.instance_members = {}
            return
        
        self.func = func = func.__get__(inst, None)
        self.inst = inst
        self.name = func.__name__
        
        # Get the function signature
        value_signature = signature(func)
        self.target = value_signature.return_annotation
        
        # Interface between data and bytes
        self.serialiser = Serialiser(self.ordered_arguments(value_signature))
        self.binder = value_signature.bind

        # Enable modifier lookup
        self.__annotations__.update(func.__annotations__)
                
    def __get__(self, inst, base):
        try:
            bound_rpc = self.instance_members[inst]
        except KeyError:
            bound_rpc = self.instance_members[inst] = type(self)(self.func, inst)
            
        return bound_rpc
    
    def __call__(self, *args, **kwargs):
        # Determines if call should be executed or bounced
        if self.target == WorldInfo.netmode:
            return self.func(*args, **kwargs)
    
    def ordered_arguments(self, sig):
        return OrderedDict((value.name, value.annotation) for value in 
               sig.parameters.values() if isinstance(value.annotation, StaticValue))
                
    def __get__(self, inst, base):
        try:
            bound_rpc = self.instance_members[inst]
        except KeyError:
            bound_rpc = self.instance_members[inst] = type(self)(self.func, inst)
            
        return bound_rpc
    
    def __call__(self, *args, **kwargs):
        # Determines if call should be executed or bounced
        if self.target == WorldInfo.netmode:
            return self.func(*args, **kwargs)

        arguments = self.binder(*args, **kwargs).arguments
        data = self.serialiser.pack(arguments)
        
        self.inst._calls.append((self, data))
    
    def execute(self, bytes_):
        # Get object network role
        local_role = self.inst.local_role
        simulated_role = Roles.simulated_proxy

        # Check if we haven't any authority
        if local_role < simulated_role:
            return
        
        # Or if we need special privileges
        elif local_role == simulated_role and not is_simulated(self):
            return
        
        # Unpack RPC
        try:
            unpacked_data = self.serialiser.unpack(bytes_)
        except Exception as err:
            print("Error unpacking RPC call {}: {}".format(self.name, err))
            
        # Execute function
        try:
            self.func(**dict(unpacked_data))
        except Exception as err:
            print("Error invoking RPC {}: {}".format(self.name, err))
                
class BaseRules:
    '''Base class for game rules'''
      
    @classmethod
    def on_connect(cls, addr):
        return
    
    @classmethod
    def on_disconnect(cls, replicable):
        return
    
    @classmethod
    def is_relevant(cls, conn, replicable):
        if replicable.remote_role is Roles.none:
            return False
        if isinstance(replicable, BaseController):
            return False
        return True
    
class PacketCollection:
    __slots__ = "members",
    
    def __init__(self, members=None):
        if members is None:
            members = []
            
        if isinstance(members, PacketCollection) or isinstance(members, Packet):
            members = members.members
        else:
            new_members = []
            for member in members:
                if isinstance(member, PacketCollection):
                    new_members.extend(member.members)
                else:
                    new_members.append(member)
                    
            members = new_members
            
        self.members = members
    
    @property
    def reliable_members(self):
        return (m for m in self.members if m.reliable)
    
    @property
    def unreliable_members(self):
        return (m for m in self.members if not m.reliable)
    
    def to_reliable(self):
        return type(self)(self.reliable_members)
    
    def to_unreliable(self):
        return type(self)(self.unreliable_members)
    
    def on_ack(self):
        for member in self.members:
            member.on_ack()
    
    def on_not_ack(self):
        for member in self.reliable_members:
            member.on_not_ack()
    
    def to_bytes(self):
        return b''.join(m.to_bytes() for m in self.members)
    
    def from_bytes(self, bytes_):
        members = self.members = []
        append = members.append
        
        while bytes_:
            packet = Packet()
            bytes_ = packet.take_from(bytes_)
            append(packet)
        
        return self
    
    def __str__(self):
        return '\n'.join(str(m) for m in self.members)
    
    def __add__(self, other):
        return type(self)(self.members + other.members)
    
    __radd__ = __add__
    
class Packet:
    __slots__ = "protocol", "payload", "reliable", "on_success", "on_failure"
    
    protocol_handler = UInt8
    size_handler = UInt8
    
    def __init__(self, protocol=None, payload=None, *, reliable=False, on_success=None, on_failure=None):    
        # Force reliability for callbacks
        if on_success or on_failure:
            reliable = True
                
        self.on_success = on_success
        self.on_failure = on_failure        
        self.protocol = protocol
        self.payload = payload
        self.reliable = reliable
    
    @property
    def members(self):
        '''Returns self as a member of a list'''
        return [self]
                
    def on_ack(self):
        '''Called when packet is acknowledged'''
        if callable(self.on_success) and self.reliable:
            self.on_success(self)
            
    def on_not_ack(self):
        '''Called when packet is dropped'''
        if callable(self.on_failure):
            self.on_failure(self)
            
    def to_bytes(self):
        '''Converts packet into bytes'''        
        data = self.protocol_handler.pack(self.protocol) + self.payload
        return self.size_handler.pack(len(data)) + data
    
    def from_bytes(self, bytes_):
        '''Returns packet instance after population
        Takes data from bytes, returns Packet()'''
        self.take_from(bytes_)
        return self
    
    def take_from(self, bytes_):
        '''Populates packet instance with data
        Returns new slice of bytes string'''
        length_handler = self.size_handler
        protocol_handler = self.protocol_handler
        
        length = length_handler.unpack_from(bytes_)
        shift = length_handler.size()

        self.protocol = protocol_handler.unpack_from(bytes_[shift:])
        proto_shift = protocol_handler.size()
        
        self.payload = bytes_[shift + proto_shift:shift + length]
        self.reliable = False
        
        return bytes_[shift + length:]
       
    def __add__(self, other):
        if not isinstance(other, self.__class__):
            raise TypeError("Cannot add packet to {}".format(type(other)))
        return PacketCollection(members=self.members + other.members)
    
    def __str__(self):
        '''Printable version of a packet'''
        to_console = ["[Packet]"]
        for key in self.__slots__:
            to_console.append("{}: {}".format(key, getattr(self, key)))
            
        return '\n'.join(to_console)
    
    __radd__ = __add__        

class Channel:
    def __init__(self, connection, replicable):
        # Store important info
        self.replicable = replicable
        self.connection = connection
        # Set initial replication to True
        self.is_initial = True     
        self.is_dead = False
        # Get network attributes
        self.attributes = {a: b for a, b in getmembers(replicable.__class__) if isinstance(b, Attribute)}
        # Sort by name (must be the same on both client and server
        self.sorted_attributes = OrderedDict((key, self.attributes[key]) for key in sorted(self.attributes))
        # Create a serialiser instance
        self.serialiser = Serialiser(self.sorted_attributes)
        # Store dictionary of complaining values
        self._complain = copy(replicable._complain)
        # Store dictionary of ids for each attribute value
        self._sent = {key: static_description(value.value) for key, value in self.attributes.items()}
    
    def get_rpc_calls(self):            
        for (method, data) in self.replicable._calls:
            packed_name = String.pack(method.name)
            yield packed_name + data, is_reliable(method)
          
        self.replicable._calls.clear() 
        
    def invoke_rpc_call(self, rpc_call):
        rpc_name = String.unpack_from(rpc_call)
        method = getattr(self.replicable, rpc_name)
        
        if not isinstance(method, RPC):
            return
        
        method.execute(rpc_call[String.size(rpc_call):]) 
                 
class ClientChannel(Channel):      
        
    def set_attributes(self, data):
        replicable = self.replicable
        
        # Create local references outside loop
        replicable_data = replicable._data
        attribute_references = self.attributes
        notifier = replicable.on_notify
        
        # Process and store new values
        for name, value in self.serialiser.unpack(data, replicable_data):
            # Get attribute reference
            attribute = attribute_references[name]
            # Store new value
            replicable_data[name] = value
            # Check if needs notification
            if attribute.notify:
                notifier(name)
                                                                                            
class ServerChannel(Channel):
        
    @property
    def is_complain(self):
        # Compare the complaining state of the replicable against the channel
        return self.replicable._complain == self._complain
    
    @is_complain.setter
    def is_complain(self, value):
        # Used to stop complaining
        if not value:
            self._complain = self.replicable._complain
        
    def get_attributes(self, is_owner):
        # Get replicable and its class
        replicable = self.replicable
        replicable_cls = replicable.__class__
        
        # Get names of replicable attributes
        can_replicate = replicable.conditions(is_owner,
                            self.is_complain,
                            self.is_initial)
                
        # List for writing data and mask information
        can_replicate = list(can_replicate)
        
        # Local access
        previous_hashes = self._sent
        current_values = replicable._data
        get_description = static_description
        
        # Store dict of name-> value
        data = {}
        
        # Iterate over attributes
        for name in can_replicate:
            
            # Get current value
            value = current_values[name]
            
            # Check if the last hash is the same
            last_hash = previous_hashes[name]
            new_hash = get_description(value)
            
            # If values match don't update
            if last_hash == new_hash:
                continue 
            
            # Add value to data dict
            data[name] = value
            
            # Hash the last sent value (for later comparison)           
            previous_hashes[name] = new_hash
        
        # Stop complaining attributes for this channel
        self.is_complain = False
        
        # We must have now replicated
        self.is_initial = False
        
        # Only send bytes if replicated
        if not data:
            return
        
        # Returns packed data
        return self.serialiser.pack(data)

class Connection:
    
    def __init__(self, netmode):
        self.netmode = netmode
        self.channels = keyeddefaultdict(self.create_channel)
        self.replicable = None
        
    def on_delete(self):
        pass
    
    def is_owner(self, replicable):  
        '''Determines if a connection owns this replicable
        Searches for Replicable with same network id as connection Controller'''  
        last = None
        # Walk the parent tree until no parent
        try:
            while replicable:
                owner = replicable.owner
                last, replicable = replicable, owner
        
        except AttributeError:
            pass
        
        # Return the condition of parent id equating to the connection controller id 
        try:                   
            return last.network_id == self.replicable.network_id        
        except AttributeError:
            return False     
           
class ClientConnection(Connection):
    
    def __init__(self, *args, **kwargs):       
        super().__init__(*args, **kwargs) 

    def notify_destroyed_replicable(self, replicable):
        self.channels.pop(replicable.network_id)
    
    def create_channel(self, network_id):
        '''Create channel for replicable with network id
        @param network_id: network id of replicable'''
        replicable = Replicable._instances[network_id]
        replicable.subscribe(self.notify_destroyed_replicable)
        return ClientChannel(self, replicable)
    
    def set_replication(self, packet, created_replicables=None):
        '''Replication function
        Accepts replication packets and responds to protocol
        @param packet: replication packet'''
        
        # If an update for a replicable
        if packet.protocol == Protocols.replication_update:
            network_id = UInt8.unpack_from(packet.payload)
            
            if network_id in Replicable._instances:
                channel = self.channels[network_id]
                channel.set_attributes(packet.payload[1:])
            
                return channel.replicable
        
        # If an RPC call
        elif packet.protocol == Protocols.method_invoke:
            network_id = UInt8.unpack_from(packet.payload)
            channel = self.channels[network_id]
            
            if self.is_owner(channel.replicable):
                channel.invoke_rpc_call(packet.payload[1:]) 
        
        # If construction for replicable
        elif packet.protocol == Protocols.replication_init:
            network_id = UInt8.unpack_from(packet.payload)
            type_name = String.unpack_from(packet.payload[1:])
            
            # If the replicable doesnt exist
            if not network_id in Replicable._instances:
                # Create replicable of same type           
                replicable_cls = Replicable._types[type_name]
                replicable = replicable_cls(network_id, register=True)
            # If it does (usually static replicables)
            else:
                replicable = Replicable._instances[network_id]
                
            # Static actors still need role switching
            created_replicables.append(replicable)
            
            # If replicable is Controller
            if isinstance(replicable, Controller):
                # Register as own replicable
                self.replicable = replicable
        
        # If it is the deletion request
        elif packet.protocol == Protocols.replication_del:
            network_id = UInt8.unpack_from(packet.payload)
            
            # If the replicable exists
            if network_id in Replicable._instances:
                replicable = Replicable._instances[network_id]
                replicable.on_delete()
    
    def send(self, network_tick):
        '''Client connection send method
        Sends data using initialised context
        Sends RPC information
        Generator'''        
        for network_id, replicable in Replicable._instances.items():
            # Determine if we own this replicable
            is_owner = self.is_owner(replicable)
            # Get network ID
            network_id = replicable.network_id
            packed_id = UInt8.pack(network_id)
            
            # Get attribute channel
            channel = self.channels[network_id]
            
            # Send RPC calls if we are the owner
            if is_owner and replicable._calls:
                for rpc_call, reliable in channel.get_rpc_calls():
                    yield Packet(protocol=Protocols.method_invoke, payload=packed_id + rpc_call, reliable=reliable)
       
    def receive(self, packets):
        '''Client connection receive method
        Receive data using initialised context
        Receive RPC and replication information
        Catches network errors'''
        created_replicables = []
    
        for packet in packets:
            
            protocol = packet.protocol

            if protocol == Protocols.replication_update:
                self.set_replication(packet)
                
            elif protocol == Protocols.method_invoke:
                self.set_replication(packet)    
                
            elif protocol == Protocols.replication_init:
                self.set_replication(packet, created_replicables)
            
            elif protocol == Protocols.replication_del:
                self.set_replication(packet)
        
        # We run this after replication to ensure relationships are valid
        if not created_replicables:
            return
        
        # For any created replicables, switch roles
        # Only owned replicables may be autonomous
        for replicable in created_replicables:
            replicable.local_role, replicable.remote_role = replicable.remote_role, replicable.local_role
            if replicable.local_role == Roles.autonomous_proxy and not self.is_owner(replicable):
                replicable.local_role = Roles.simulated_proxy
        
class ServerConnection(Connection):
    
    def __init__(self, *args, **kwargs):  
        super().__init__(*args, **kwargs)
    
    def on_delete(self):
        '''Delete callback
        Called on delete of connection'''
        super().on_delete()
        
        # If we own a controller destroy it
        if self.replicable:
            self.replicable.on_delete()
            # We must be connected to have a controller
            print("disconnected!".format(getattr(self.replicable, 'name', "")))
                
    def create_channel(self, network_id):
        """Creates a replication channel for replicable"""
        replicable =  Replicable._instances[network_id]
        replicable.subscribe(self.notify_destroyed_replicable)
        return ServerChannel(self, replicable)
    
    def notify_destroyed_replicable(self, replicable):
        '''Called when replicable dies
        @param replicable: replicable that died'''
        if replicable.network_id in self.channels:
            self.channels[replicable.network_id].is_dead = True
            
    def get_method_replication(self):
        for replicable in Replicable._instances.values():
            # Determine if we own this replicable
            is_owner = self.is_owner(replicable)
            
            # Get network ID
            network_id = replicable.network_id
            packed_id = UInt8.pack(network_id)
            
            # Get attribute channel
            channel = self.channels[network_id]
            
            # if the channel is dead
            if channel.is_dead:
                continue
            
            # Send RPC calls if we are the owner
            if is_owner and replicable._calls:
                for rpc_call, reliable in channel.get_rpc_calls():
                    yield Packet(protocol=Protocols.method_invoke, payload=packed_id + rpc_call, reliable=reliable)
                     
    def get_full_replication(self):
        '''Yields replication packets for relevant replicable
        @param replicable: replicable to replicate'''
        is_relevant = WorldInfo.rules.is_relevant

        for replicable in WorldInfo.actors:
            # Determine if we own this replicable
            is_owner = self.is_owner(replicable)
            
            # Get network ID
            network_id = replicable.network_id
            packed_id = UInt8.pack(network_id)
            
            # Get attribute channel
            channel = self.channels[network_id]
            
            # if the channel is dead
            if channel.is_dead:
                # Remove it
                self.channels.pop(network_id)
                # Send delete packet    
                yield Packet(protocol=Protocols.replication_del, payload=packed_id, reliable=True) 
                # Don't process rest              
                continue

            # Send RPC calls if we are the owner
            if is_owner and replicable._calls:
                for rpc_call, reliable in channel.get_rpc_calls():
                    yield Packet(protocol=Protocols.method_invoke, payload=packed_id + rpc_call, reliable=reliable)
            
            # Only send attributes if relevant
            if is_owner or is_relevant(self, replicable):
                # If we've never replicated to this channel
                if channel.is_initial:
                    # Pack the class name
                    packed_class = String.pack(type(replicable).__name__)
                    # Send the protocol, class name and owner status to client
                    yield Packet(protocol=Protocols.replication_init, payload=packed_id + packed_class, reliable=True)
             
                # Send changed attributes
                attributes = channel.get_attributes(is_owner)
                # If they have changed                    
                if attributes:
                    yield Packet(protocol=Protocols.replication_update, 
                            payload=packed_id + attributes, reliable=True)
                                 
    def receive(self, packets):
        '''Server connection receive method
        Receive data using initialised context
        Receive RPC information'''
        # Local space variables
        is_owner = self.is_owner
        channels = self.channels
        
        # Run RPC invoke for each packet
        for packet in packets:
            # If it is an RPC packet
            if packet.protocol == Protocols.method_invoke:
                # Unpack data
                network_id = UInt8.unpack_from(packet.payload)
                channel = channels[network_id]
                
                # If we have permission to execute
                if is_owner(channel.replicable):
                    channel.invoke_rpc_call(packet.payload[1:])
    
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

class ConnectionInterface:
    
    _instances = {}
    
    def __init__(self, addr):
        # Maximum sequence number value
        self.sequence_max_size = 255 ** 2
        self.sequence_handler = smallest_int_handler(self.sequence_max_size)
        
        # Number of packets to ack per packet
        self.ack_window = 32
        self.window_config = list(repeat(False, self.ack_window))
        
        # Bitfield and bitfield size
        self.ack_bitfield = bitarray(self.window_config)
        self.ack_size = bits2bytes(self.ack_window)
        
        # Protocol unpacker
        self.protocol_handler = UInt8
        self.ack_value_handler = UInt8
        
        # Storage for packets requesting ack or received
        self.requested_ack = {}
        self.received_window = deque()
        
        # Current indicators of latest out/incoming sequence numbers
        self.local_sequence = 0
        self.remote_sequence = 0
        
        # Time out for connection before it is deleted
        self.time_out = 4
        self.last_received = time() 
        
        # Simple connected status
        self.status = ConnectionStatus.disconnected
        
        # Maintains an actual connection
        self.connection = None
        
        self.buffer = []
        
        # Maintenance info
        self._addr = addr
        self._instances[addr] = self
    
    def __new__(cls, *args, **kwargs):
        """Constructor switch depending upon netmode"""
        if cls is ConnectionInterface:
            netmode = WorldInfo.netmode
            
            if netmode == Netmodes.server:
                return ServerInterface.__new__(ServerInterface, *args, **kwargs)
            
            elif netmode == Netmodes.client:
                return ClientInterface.__new__(ClientInterface,*args, **kwargs)
        else:
            return super().__new__(cls)
        
    def on_delete(self):
        self._instances.pop(self._addr)
        
        if self.connection:
            self.connection.on_delete()
       
    @property
    def next_local_sequence(self):
        self.local_sequence = (self.local_sequence + 1) if (self.local_sequence < self.sequence_max_size) else 0
        return self.local_sequence
        
    def set_time_out(self, delay):
        self.time_out = delay
    
    def sequence_more_recent(self, s1, s2):
        half_seq = (self.sequence_max_size / 2)
        return ((s1 > s2) and (s1 - s2) <= half_seq) or ((s2 > s1) and (s2 - s1) > half_seq) 
    
    def delete(self):
        self.status = ConnectionStatus.deleted
        
    def connected(self, *args, **kwargs):
        self.status = ConnectionStatus.connected
    
    def send(self, network_tick):    
        
        # Check for timeout
        if (time() - self.last_received) > self.time_out:
            self.status = ConnectionStatus.timeout
            print("timeout")
            
        # If not connected setup handshake
        if self.status == ConnectionStatus.disconnected:
            packets = self.get_handshake()
            self.status = ConnectionStatus.handshake
        
        # If connected send normal data
        elif self.status == ConnectionStatus.connected:
            packets = self.connection.send(network_tick)
        
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
        ack_bitfield = bitarray(self.window_config)
        
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
        ack_info = self.sequence_handler.pack(sequence)
        ack_info += self.sequence_handler.pack(remote_sequence)
        ack_info += ack_bitfield.tobytes()
        
        # Store acknowledge request for reliable members of packet
        self.requested_ack[sequence] = packet_collection
        
        # Return the packet as bytes
        return ack_info + packet_collection.to_bytes()

    def receive(self, bytes_):
        sequence = self.sequence_handler.unpack_from(bytes_)
        bytes_ = bytes_[self.sequence_handler.size():]
        
        # Get the base value for the bitfield
        ack_base = self.sequence_handler.unpack_from(bytes_)
        bytes_ = bytes_[self.sequence_handler.size():]
        
        # Read the acknowledgement bitfield
        ack_bitfield = bitarray(); ack_bitfield.frombytes(bytes_[:self.ack_size])
        
        # Recreate packet collection
        packet_collection = PacketCollection().from_bytes(bytes_[self.ack_size:])
    
        # Store the received time
        self.last_received = time()
        
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
        
        # Iterate over ACK bitfield
        for index in range(self.ack_window):
            sequence = ack_base - (index + 1)
            
            # If it was ackked successfully
            flag = ack_bitfield[index]
                        
            # If we are waiting for this packet, acknowledge it
            if (flag and sequence in requested_ack):
                requested_ack.pop(sequence).on_ack()                
        
        # Acknowledge the sequence of this packet about
        if ack_base in self.requested_ack:
            requested_ack.pop(ack_base).on_ack()
        
        # If the packet drops off the ack_window assume it is lost
        likely_dropped = [k for k in requested_ack.keys() if (sequence - k) > self.ack_window]
        
        # Find packets we think are dropped and resend them
        for sequence in likely_dropped:
            # Only reliable members asked to be informed if received/dropped
            reliable_collection = requested_ack.pop(sequence).to_reliable()
            reliable_collection.on_not_ack()
            self.buffer.append(reliable_collection)
                
        # Call post-processer receive
        if self.status != ConnectionStatus.connected:
            for member in packet_collection.members:
  
                if member.protocol > Protocols.request_auth:
                    continue
               
                self.receive_handshake(member)
        
        else:
            self.connection.receive(packet_collection.members)

class ServerInterface(ConnectionInterface):
    
    def __init__(self, addr):
        super().__init__(addr)
        
        self.auth_error = None
    
    def get_handshake(self):
        '''Will only exist if invoked'''
        connection_failed = self.connection is None
        
        if connection_failed:
            # Send the error code
            error_name = type(self.auth_error).__name__
    
            error_body = self.auth_error.args[0] if self.auth_error.args else ""
            
            # Yield reliable packet
            return Packet(protocol=Protocols.auth_failure, payload=String.pack(error_name) + String.pack(error_body), on_success=self.delete)
        
        else:
            # Send acknowledgement
            return Packet(protocol=Protocols.auth_success, payload=UInt8.pack(WorldInfo.netmode), 
                          on_success=self.connected)
            
    def receive_handshake(self, packet):
        # Unpack data
        netmode = UInt8.unpack_from(packet.payload)
        
        # Store replicable
        try:
            WorldInfo.rules.pre_initialise(netmode)
        
        # If a NetworkError is raised, store result
        except NetworkError as err:
            self.auth_error = err            
            return 
    
        self.connection = ServerConnection(netmode)
        
        self.connection.replicable = WorldInfo.rules.post_initialise(self.connection)

class ClientInterface(ConnectionInterface):
    
    def __init__(self, addr):
        super().__init__(addr)
        
    def get_handshake(self):
        return Packet(protocol=Protocols.request_auth, payload=UInt8.pack(WorldInfo.netmode), reliable=True)
    
    def receive_handshake(self, packet):
        protocol = packet.protocol

        if protocol == Protocols.auth_failure:
            error_type = String.unpack_from(packet.payload)
            shift = String.size(packet.payload)
            error_body = String.unpack_from(packet.payload[shift:])
            raise NetworkError._types[error_type](error_body)
        
        # Get remote network mode
        netmode = UInt8.unpack_from(packet.payload)

        # Must be success
        self.connection = ClientConnection(netmode)
        
        self.connected()
        
class System:
    _instances = set()
    
    def __init__(self):
        self._instances.add(self)
        self.active = True
    
    def delete(self):
        self._instances.remove(self)
    
    def pre_update(self, delta_time):
        pass
    
    def post_update(self, delta_time):
        pass
    
class DeltaTime:
    def __init__(self):
        self.last = time()
    
    def __enter__(self):
        new_time = time()
        delta_time = new_time - self.last
        self.last = new_time
        return delta_time
    
    def __exit__(self, type, value, traceback):
        pass
                
class GameLoop(socket):
    
    def __init__(self, addr, port, update_interval=1/15):
        '''Network socket initialiser'''
        super().__init__(AF_INET, SOCK_DGRAM)
        
        self.bind((addr, port))
        self.setblocking(False)
        
        self._interval = update_interval
        self._last_sent = 0.0
        self._started = time()
        self._clock = DeltaTime()
        
        self.sent_bytes = 0
        self.received_bytes = 0
    
    @property
    def can_send(self):
        '''Determines if the socket can send 
        Result according to time elapsed >= send interval'''
        return (time() - self._last_sent) >= self._interval
    
    @property
    def send_rate(self):
        return (self.sent_bytes / (time() - self._started))
    
    @property
    def receive_rate(self):
        return (self.received_bytes / (time() - self._started))
    
    def connections_by_status(self, status, comparator=operator.eq):   
        count = 0
        for interface in ConnectionInterface._instances.values():
            if comparator(interface.status, status):
                count += 1
        return count
    
    def stop(self):
        self.close()
                
    def stop(self):
        self.close()
            
    def sendto(self, *args, **kwargs):
        '''Overrides sendto method to record sent time'''
        result = super().sendto(*args, **kwargs)
        self.sent_bytes += result
        return result
    
    def receive_from(self, buff_size=63553):
        '''A partial function for recvfrom
        Used in iter(func, sentinel)'''
        try:
            return self.recvfrom(buff_size)
        except socket_error:
            return    
    
    def receive(self):
        '''Receive all data from socket'''
        # Get connections
        connections = ConnectionInterface._instances
        
        # Receives all incoming data
        for bytes_, addr in iter(self.receive_from, None):
            try:
                connection = connections[addr]
            except KeyError:
                connection = ConnectionInterface(addr)
            
            connection.receive(bytes_)
            self.received_bytes += len(bytes_)
        
    def send(self):
        '''Send all connection data and update timeouts'''
        # A switch between emergency and normal
        network_tick = self.can_send
        
        # Get connections
        connections = ConnectionInterface._instances
        to_delete = []
       
        # Send all queued data
        for addr, connection in connections.items():
            
            # If the connection should be removed (timeout or explicit)
            if connection.status < ConnectionStatus.disconnected:
                to_delete.append(connection)
                continue
            
            # Give the option to send nothing
            data = connection.send(network_tick)
            
            # If returns data, send it
            if data:
                self.sendto(data, addr) 
                
        # Delete dead connections
        if to_delete:
            for connection in to_delete:
                connection.on_delete()

        # Remember last non urgent
        if network_tick:
            self._last_sent = time()
    
    def connect_to(self, conn):
        return ConnectionInterface(conn)
    
    def update(self):        
        self.receive()

        Replicable._update_graph()
        
        with self._clock as delta_time:
            
            for system in System._instances:
                if system.active:
                    system.pre_update(delta_time)
            
            for actor in WorldInfo.actors:
                if (actor.local_role > Roles.simulated_proxy) or (actor.local_role == Roles.simulated_proxy and is_simulated(actor.update)):
                    actor.update(delta_time)
    
                if hasattr(actor, "player_input") and isinstance(actor, Controller):
                    actor.player_update(delta_time)
                
            for system in System._instances:
                if system.active:
                    system.post_update(delta_time)
            
        self.send()
        
WorldInfo = BaseWorldInfo(255, register=True)
