from .conditions import is_reliable
from .type_flag import TypeFlag
from .decorators import with_tag
from .enums import Netmodes
from .flag_serialiser import FlagSerialiser
from .handlers import static_description, get_handler
from .tagged_delegate import DelegateByNetmode
from .replicable import Replicable

from functools import partial
from time import clock

__all__ = ['Channel', 'ClientChannel', 'ServerChannel']


class Channel(DelegateByNetmode):
    """Channel for replication information.

    Belongs to an instance of Replicable and a connection
    """

    subclasses = {}

    def __init__(self, stream, replicable):
        # Store important info
        self.replicable = replicable
        self.stream = stream
        # Set initial (replication status) to True
        self.last_replication_time = 0.0
        self.is_initial = True

        # Get network attributes
        self.attribute_storage = replicable._attribute_container
        self.rpc_storage = replicable._rpc_container

        # Create a serialiser instance
        self.logger = stream.logger.getChild("<Channel: {}>".format(repr(replicable)))
        self.serialiser = FlagSerialiser(self.attribute_storage._ordered_mapping,
                                         logger=self.logger.getChild("<FlagSerialiser>"))

        self.rpc_id_packer = get_handler(TypeFlag(int))
        self.replicable_id_packer = get_handler(TypeFlag(Replicable))
        self.packed_id = self.replicable_id_packer.pack(replicable)

    @property
    def is_owner(self):
        """Return True if this channel is in the ownership tree of the connection replicable"""
        parent = self.replicable.uppermost

        try:
            return parent == self.stream.replicable

        except AttributeError:
            return False

    def take_rpc_calls(self):
        """Return the requested RPC calls in a packaged format:

        rpc_id (bytes) + body (bytes), reliable status (bool)
        """
        id_packer = self.rpc_id_packer.pack
        get_reliable = is_reliable

        storage_data = self.rpc_storage.data

        for (method, data) in storage_data:
            yield id_packer(method.rpc_id) + data, get_reliable(method)

        storage_data.clear()

    def invoke_rpc_call(self, rpc_call):
        """Invoke an RPC call from packaged format

        :param rpc_call: rpc data (see take_rpc_calls)
        """
        rpc_id, rpc_header_size = self.rpc_id_packer.unpack_from(rpc_call)

        try:
            method = self.rpc_storage.functions[rpc_id]

        except IndexError:
            self.logger.exception("Error invoking RPC: No RPC function with id {}".format(rpc_id))

        else:
            method.execute(rpc_call[rpc_header_size:])

    @property
    def has_rpc_calls(self):
        """Return True if replicable has outgoing RPC calls"""
        return bool(self.rpc_storage.data)


@with_tag(Netmodes.client)
class ClientChannel(Channel):

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

    def set_attributes(self, bytes_string, offset=0):
        """Unpack byte stream and updates attributes

        :param bytes\_: byte stream of attribute
        """
        # Create local references outside loop
        replicable_data = self.attribute_storage.data
        get_attribute = self.attribute_storage.get_member_by_name
        notifications = []
        notify = notifications.append

        for attribute_name, value in self.serialiser.unpack(bytes_string, replicable_data, offset=offset):
            attribute = get_attribute(attribute_name)

            # Store new value
            replicable_data[attribute] = value

            # Check if needs notification
            if attribute.notify:
                notify(attribute_name)

        # Notify after all values are set
        if notifications:
            return partial(self.notify_callback, notifications)


@with_tag(Netmodes.server)
class ServerChannel(Channel):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.hash_dict = self.attribute_storage.get_default_descriptions()
        self.complaint_dict = self.attribute_storage.get_default_complaints()

    @property
    def replication_priority(self):
        """Get the replication priority for a replicable
        Utilises replication interval to increment priority of neglected replicables.

        :returns: replication priority
        """
        interval = (clock() - self.last_replication_time)
        elapsed_fraction = (interval / self.replicable.replication_update_period)
        return self.replicable.replication_priority + (elapsed_fraction - 1)

    @property
    def awaiting_replication(self):
        """Return True if the channel is due to replicate its state"""
        interval = (clock() - self.last_replication_time)
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

            complaint_hashes = self.attribute_storage.complaints
            is_complaining = previous_complaints != complaint_hashes

            # Get names of Replicable attributes
            can_replicate = replicable.conditions(is_owner, is_complaining, self.is_initial)

            get_description = static_description
            get_attribute = self.attribute_storage.get_member_by_name
            attribute_data = self.attribute_storage.data

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
            self.last_replication_time = clock()
            self.is_initial = False

            # An output of bytes asserts we have data
            if to_serialise:
                # Returns packed data
                data = self.serialiser.pack(to_serialise)

            else:
                data = None

        return data
