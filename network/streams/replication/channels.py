from functools import partial
from time import clock

from ...annotations.conditions import is_reliable
from ...type_flag import TypeFlag
from ...flag_serialiser import FlagSerialiser
from ...handlers import static_description, get_handler
from ...replicable import Replicable
from ...signals import SignalListener, ReplicableRegisteredSignal, ReplicableUnregisteredSignal

__all__ = ['ReplicableChannelBase', 'ClientChannel', 'ServerChannel']


class ReplicableChannelBase:
    """Channel for replication information.

    Belongs to an instance of Replicable and a connection
    """

    id_handler = get_handler(TypeFlag(Replicable))

    def __init__(self, scene_channel, replicable):
        # Store important info
        self.replicable = replicable
        self.scene_channel = scene_channel

        # Set initial (replication status) to True
        self._last_replication_time = 0.0
        self.is_initial = True

        # Get network attributes
        self._attribute_storage = replicable._attribute_container
        self._rpc_storage = replicable._rpc_container

        # Create a serialiser instance
        self.logger = scene_channel.logger.getChild("<Channel: {}>".format(repr(replicable)))
        self._serialiser = FlagSerialiser(self._attribute_storage._ordered_mapping,
                                         logger=self.logger.getChild("<FlagSerialiser>"))

        self._rpc_id_handler = get_handler(TypeFlag(int))
        self.packed_id = self.__class__.id_handler.pack(replicable)

    @property
    def is_owner(self):
        """Return True if this channel is in the ownership tree of the connection replicable"""
        parent = self.replicable.uppermost

        try:
            return parent == self.scene_channel.replicable

        except AttributeError:
            return False

    def dump_rpc_calls(self):
        """Return the requested RPC calls in a packaged format:

        rpc_id (bytes) + body (bytes), reliable status (bool)
        """
        id_packer = self._rpc_id_handler.pack
        get_reliable = is_reliable

        storage_data = self._rpc_storage.data

        reliable_rpc_calls = []
        unreliable_rpc_calls = []

        for (method, data) in storage_data:
            packed_rpc_call = id_packer(method.rpc_id) + data

            if get_reliable(method):
                reliable_rpc_calls.append(packed_rpc_call)
            else:
                unreliable_rpc_calls.append(packed_rpc_call)

        storage_data.clear()
        return reliable_rpc_calls, unreliable_rpc_calls

    def invoke_rpc_calls(self, data):
        """Invoke an RPC call from packaged format

        :param rpc_call: rpc data (see take_rpc_calls)
        """
        while data:
            rpc_id, rpc_header_size = self._rpc_id_handler.unpack_from(data)

            unpacked_bytes = 0

            try:
                method = self._rpc_storage.functions[rpc_id]

            except IndexError:
                self.logger.exception("Error invoking RPC: No RPC function with id {}".format(rpc_id))
                break

            else:
                unpacked_bytes = method.execute(data[rpc_header_size:])

            data = data[unpacked_bytes:]


class ClientReplicableChannel(ReplicableChannelBase):

    def notify_callback(self, notifications):
        invoke_notify = self.replicable.on_notify
        for attribute_name in notifications:
            invoke_notify(attribute_name)

    @property
    def replication_priority(self):
        """Get the replication priority for a replicable.
        Utilises replication interval to increment priority of neglected replicables.

        :returns: replication priority
        """
        return self.replicable.replication_priority

    def read_attributes(self, bytes_string, offset=0):
        """Unpack byte stream and updates attributes

        :param bytes\_: byte stream of attribute
        """
        # Create local references outside loop
        replicable_data = self._attribute_storage.data
        get_attribute = self._attribute_storage.get_member_by_name

        notifications = []
        notify = notifications.append

        unpacked_items, read_bytes = self._serialiser.unpack(bytes_string, replicable_data, offset=offset)

        for attribute_name, value in unpacked_items:
            attribute = get_attribute(attribute_name)

            # Store new value
            replicable_data[attribute] = value

            # Check if needs notification
            if attribute.notify:
                notify(attribute_name)

        # Notify after all values are set
        notifier = partial(self.notify_callback, notifications)

        return notifier, read_bytes


class ServerReplicableChannel(ReplicableChannelBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.hash_dict = self._attribute_storage.get_default_descriptions()
        self.complaint_dict = self._attribute_storage.get_default_complaints()

    @property
    def replication_priority(self):
        """Get the replication priority for a replicable
        Utilises replication interval to increment priority of neglected replicables.

        :returns: replication priority
        """
        interval = (clock() - self._last_replication_time)
        elapsed_fraction = (interval / self.replicable.replication_update_period)
        return self.replicable.replication_priority + (elapsed_fraction - 1)

    @property
    def is_awaiting_replication(self):
        """Return True if the channel is due to replicate its state"""
        interval = (clock() - self._last_replication_time)
        return (interval >= self.replicable.replication_update_period) or self.is_initial

    def get_attributes(self, is_owner):
        """Return the serialised state of the managed network object"""
        # Get Replicable and its class
        replicable = self.replicable

        # Set role context
        with replicable.roles.set_context(is_owner):

            # Local access
            previous_hashes = self.hash_dict
            previous_complaints = self.complaint_dict

            complaint_hashes = self._attribute_storage.complaints
            is_complaining = previous_complaints != complaint_hashes

            # Get names of Replicable attributes
            can_replicate = replicable.conditions(is_owner, is_complaining, self.is_initial)

            get_description = static_description
            get_attribute = self._attribute_storage.get_member_by_name
            attribute_data = self._attribute_storage.data

            # Store dict of attribute-> value
            to_serialise = {}

            # Iterate over attributes
            for name in can_replicate:
                # Get current value
                attribute = get_attribute(name)
                value = attribute_data[attribute]

                # Check if the last hash is the same
                last_hash = previous_hashes[attribute]

                # Get value hash
                # Use the complaint hash if it is there to save computation
                new_hash = complaint_hashes[attribute] if (attribute in complaint_hashes) else get_description(value)

                # If values match, don't update
                if last_hash == new_hash:
                    continue

                # Add value to data dict
                to_serialise[name] = value

                # Remember hash of value
                previous_hashes[attribute] = new_hash

                # Set new complaint hash if it was complaining
                if attribute.complain and attribute in complaint_hashes:
                    previous_complaints[attribute] = new_hash

            # We must have now replicated
            self._last_replication_time = clock()
            self.is_initial = False

            # An output of bytes asserts we have data
            if to_serialise:
                # Returns packed data
                data = self._serialiser.pack(to_serialise)

            else:
                data = None

        return data


class SceneChannelBase(SignalListener):

    channel_class = None
    id_handler = get_handler(TypeFlag(int))

    def __init__(self, connection, scene):
        self.scene = scene
        self.connection = connection

        self.logger = connection.logger.getChild("SceneChannel")

        self.packed_id = self.__class__.id_handler.pack(scene.instance_id)
        self.replicable_channels = {}

        # Channels may be created after replicables were instantiated
        with scene:
            self.register_signals()
            self.register_existing_replicables()

    def register_existing_replicables(self):
        """Load existing registered replicables"""
        for replicable in Replicable:
            self.on_replicable_registered(replicable)

    @ReplicableRegisteredSignal.on_global
    def on_replicable_registered(self, target):
        self.replicable_channels[target.instance_id] = self.channel_class(self, target)

    @ReplicableUnregisteredSignal.on_global
    def on_replicable_unregistered(self, target):
        self.replicable_channels.pop(target.instance_id)


class ServerSceneChannel(SceneChannelBase):

    channel_class = ServerReplicableChannel

    def __init__(self, connection, scene):
        super().__init__(connection, scene)

        self.is_initial = True


class ClientSceneChannel(SceneChannelBase):

    channel_class = ClientReplicableChannel
