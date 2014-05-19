from .conditions import is_reliable
from .descriptors import TypeFlag
from .decorators import netmode_switch
from .enums import Netmodes
from .flag_serialiser import FlagSerialiser
from .handler_interfaces import static_description, get_handler
from .logger import logger
from .netmode_switch import NetmodeSwitch
from .replicable import Replicable

from functools import partial
from time import monotonic

__all__ = ['Channel', 'ClientChannel', 'ServerChannel']


class Channel(NetmodeSwitch):
    """Channel for replication information
    Belongs to an instance of Replicable and a connection"""

    subclasses = {}

    def __init__(self, connection, replicable):
        # Store important info
        self.replicable = replicable
        self.connection = connection
        # Set initial (replication status) to True
        self.last_replication_time = 0.0
        self.is_initial = True
        # Get network attributes
        self.attribute_storage = replicable._attribute_container
        # Create a serialiser instance
        self.serialiser = FlagSerialiser(
                                     self.attribute_storage._ordered_mapping)

        self.rpc_id_packer = get_handler(TypeFlag(int))
        self.replicable_id_packer = get_handler(TypeFlag(Replicable))
        self.packed_id = self.replicable_id_packer.pack(replicable)

    @property
    def is_owner(self):
        parent = self.replicable.uppermost

        try:
            return parent.instance_id == \
                self.connection.replicable.instance_id

        except AttributeError:
            return False

    def take_rpc_calls(self):
        """Returns the requested RPC calls in a packaged format
        Format: rpc_id (bytes) + body (bytes), reliable status (bool)"""
        id_packer = self.rpc_id_packer.pack
        get_reliable = is_reliable

        storage_data = self.replicable.rpc_storage.data

        for (method, data) in storage_data:
            yield id_packer(method.rpc_id) + data, get_reliable(method)

        storage_data.clear()

    def invoke_rpc_call(self, rpc_call):
        """Invokes an RPC call from packaged format

        :param rpc_call: rpc data (see take_rpc_calls)"""
        rpc_id = self.rpc_id_packer.unpack_from(rpc_call)

        try:
            method = self.replicable.rpc_storage.functions[rpc_id]

        except IndexError:
            logger.exception("Error invoking RPC: No RPC function with id {}".format(rpc_id))

        else:
            method.execute(rpc_call[self.rpc_id_packer.size():])

    @property
    def has_rpc_calls(self):
        """Returns True if replicable has outgoing RPC calls"""
        return bool(self.replicable.rpc_storage.data)


@netmode_switch(Netmodes.client)
class ClientChannel(Channel):

    def notify_callback(self, notifications):
        invoke_notify = self.replicable.on_notify
        for attribute_name in notifications:
            invoke_notify(attribute_name)

    @property
    def replication_priority(self):
        """Gets the replication priority for a replicable
        Utilises replication interval to increment priority
        of neglected replicables

        :returns: replication priority"""
        return self.replicable.replication_priority

    def set_attributes(self, bytes_string):
        """Unpacks byte stream and updates attributes

        :param bytes\_: byte stream of attribute"""
        replicable = self.replicable

        # Create local references outside loop
        replicable_data = self.attribute_storage.data
        get_attribute = self.attribute_storage.get_member_by_name
        notifications = []
        notify = notifications.append

        for attribute_name, value in self.serialiser.unpack(bytes_string,
                                                            replicable_data):
            attribute = get_attribute(attribute_name)
            # Store new value
            replicable_data[attribute] = value

            # Check if needs notification
            if attribute.notify:
                notify(attribute_name)

        # Process and store new values

        # Notify after all values are set
        if notifications:
            return partial(self.notify_callback, notifications)


@netmode_switch(Netmodes.server)
class ServerChannel(Channel):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.hash_dict = self.attribute_storage.get_default_descriptions()
        self.complaint_dict = self.attribute_storage.get_default_complaints()

    @property
    def replication_priority(self):
        """Gets the replication priority for a replicable
        Utilises replication interval to increment priority
        of neglected replicables

        :returns: replication priority"""
        interval = (monotonic() - self.last_replication_time)
        elapsed_fraction = (interval / self.replicable.replication_update_period)
        return self.replicable.replication_priority + (elapsed_fraction - 1)

    @property
    def awaiting_replication(self):
        interval = (monotonic() - self.last_replication_time)
        return ((interval >= self.replicable.replication_update_period)
                or self.is_initial)

    def get_attributes(self, is_owner):
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
            can_replicate = replicable.conditions(is_owner,
                                                  is_complaining,
                                                  self.is_initial)

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
                new_hash = complaint_hashes[attribute] if (attribute in
                           complaint_hashes) else get_description(value)

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
            self.last_replication_time = monotonic()
            self.is_initial = False

            # Outputting bytes asserts we have data
            if to_serialise:
                # Returns packed data
                data = self.serialiser.pack(to_serialise)

            else:
                data = None

        return data
