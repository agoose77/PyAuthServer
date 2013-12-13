from .handler_interfaces import static_description, get_handler
from .argument_serialiser import ArgumentSerialiser
from .conditions import is_reliable
from .descriptors import StaticValue
from .replicables import Replicable, WorldInfo


class Channel:

    def __init__(self, connection, replicable):
        # Store important info
        self.replicable = replicable
        self.connection = connection
        # Set initial (replication status) to True
        self.last_replication_time = WorldInfo.elapsed
        self.is_initial = True
        # Get network attributes
        self.attribute_storage = replicable.attribute_storage
        # Sort by name (must be the same on both client and server)
        self.sorted_attributes = self.attribute_storage.get_ordered_members()
        # Create a serialiser instance
        self.serialiser = ArgumentSerialiser(self.sorted_attributes)

        self.rpc_id_packer = get_handler(StaticValue(int))
        self.replicable_id_packer = get_handler(StaticValue(Replicable))

        self.packed_id = self.replicable_id_packer.pack(replicable)

    def take_rpc_calls(self):
        '''Returns the requested RPC calls in a packaged format
        Format: rpc_id (bytes) + payload (bytes), reliable status (bool)'''
        id_packer = self.rpc_id_packer.pack
        get_reliable = is_reliable

        storage_data = self.replicable.rpc_storage.data

        for (method, data) in storage_data:
            yield id_packer(method.rpc_id) + data, get_reliable(method)

        storage_data.clear()

    def invoke_rpc_call(self, rpc_call):
        '''Invokes an rpc call from packaged format
        @param rpc_call: rpc data (see take_rpc_calls)'''
        rpc_id = self.rpc_id_packer.unpack_from(rpc_call)

        if not self.replicable.registered:
            return

        try:
            method = self.replicable.rpc_storage.functions[rpc_id]

        except IndexError:
            print("Error invoking RPC: No RPC function with id {}".format(
                                                                      rpc_id))
        else:
            method.execute(rpc_call[self.rpc_id_packer.size():])

    @property
    def has_rpc_calls(self):
        '''Returns True if replicable has outgoing RPC calls'''
        return bool(self.replicable.rpc_storage.data)


class ClientChannel(Channel):

    def set_attributes(self, data):
        replicable = self.replicable

        # Create local references outside loop
        replicable_data = replicable.attribute_storage.data
        get_attribute = replicable.attribute_storage.get_member_by_name
        notifications = []
        notify = notifications.append
        invoke_notify = replicable.on_notify

        # Process and store new values
        for attribute_name, value in self.serialiser.unpack(data,
                                                    replicable_data):
            attribute = get_attribute(attribute_name)
            # Store new value
            replicable_data[attribute] = value

            # Check if needs notification
            if attribute.notify:
                notify(attribute_name)

        # Notify after all values are set
        if notifications:
            for attribute_name in notifications:
                invoke_notify(attribute_name)


class ServerChannel(Channel):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        #=====================================================================
        # Store dictionary of complaint values to compare replicable's account
        # Data may changed from default values
        #======================================================================
        self.hash_dict = self.attribute_storage.get_default_descriptions()
        self.complaint_dict = self.attribute_storage.get_default_complaints()

    def get_attributes(self, is_owner, replication_time):
        # Get Replicable and its class
        replicable = self.replicable

        # Set the role context for whom we replicate
        replicable.roles.context = is_owner

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
        self.last_replication_time = replication_time
        self.is_initial = False

        # Outputting bytes asserts we have data
        if to_serialise:
            # Returns packed data
            data = self.serialiser.pack(to_serialise)

        else:
            data = None

        replicable.roles.context = None
        return data
