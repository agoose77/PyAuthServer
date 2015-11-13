from network.bitfield import BitField
from network.type_serialisers import get_serialiser, get_serialiser_for

__all__ = ["FlagSerialiser"]


class FlagSerialiser:
    """Interface class for parsing/dumping data to bytes
    Packed member order: Contents, Data, Booleans, Nones
    """

    # The last two entries of the contents mask 
    NONE_CONTENT_INDEX = -1
    BOOL_CONTENT_INDEX = -2

    def __init__(self, arguments, logger=None):
        """FlagSerialiser initialiser

        :param arguments: ordered dict of named TypeInfo instances
        :param logger: logger instance for handlers
        """
        self.bool_args = [(key, flag) for key, flag in arguments.items() if flag.data_type is bool]
        self.non_bool_args = [(key, flag) for key, flag in arguments.items() if flag.data_type is not bool]
        self.non_bool_handlers = [(key, get_serialiser(flag, logger=logger.getChild(repr(key)) if logger else None))
                                  for key, flag in self.non_bool_args]

        self.enumerated_non_bool_handlers = list(enumerate(self.non_bool_handlers))
        self.enumerated_bool_args = list(enumerate(self.bool_args))

        # Maintain count of data types
        self.total_none_booleans = len(self.non_bool_args)
        self.total_booleans = len(self.bool_args)
        self.total_contents = self.total_none_booleans + self.total_booleans

        # BitFields used for packing
        self.bool_bits = BitField(self.total_booleans)
        self.none_bits = BitField(self.total_contents)

        # Additional two bits when including NoneType and Boolean values
        self.content_bits = BitField(self.total_contents + 2)

        self.boolean_packer = get_serialiser_for(BitField, fields=self.total_booleans)
        self.contents_packer = get_serialiser_for(BitField, fields=len(self.content_bits))

    def report_information(self, bytes_string, offset=0):
        """Display the contents of a serialised stream

        :param bytes_string: data to interpret
        :param offset: offset from start of stream
        """
        content_packer = self.contents_packer
        # Get header of packed data
        content_bitfield, contents_size = content_packer.unpack_from(bytes_string, offset)
        offset += contents_size

        content_bits = content_bitfield[:]

        print("Header Data: ", bytes_string[:offset])
        entry_names, entry_handlers = zip(*(self.non_bool_args + self.bool_args))

        # If there are NoneType values they will be first
        if content_bits[self.NONE_CONTENT_INDEX]:
            none_bits, none_size = content_packer.unpack_from(bytes_string, offset)
            offset += none_size

            print("NoneType Values Data: ", bytes_string[:offset], none_bits)

        else:
            none_bits = [False] * self.total_contents

        print()
        for name, included, is_none, handler in zip(entry_names, content_bits, none_bits, entry_handlers):
            if not included:
                continue

            print("{} : {}".format(name, "None" if is_none else handler.data_type.__name__))

        print()

    def _read_contents(self, bytes_string, offset):
        """Determine the included entries of the packed data

        :param bytes_string: packed data
        """
        contents_packer = self.contents_packer
        contents_size = contents_packer.unpack_merge(self.content_bits, bytes_string, offset)
        return contents_size

    def _read_nonetype_values(self, bytes_string, offset):
        """Determine the NoneType entries of the packed data

        :param bytes_string: packed data
        """
        contents_packer = self.contents_packer
        contents_size = contents_packer.unpack_merge(self.none_bits, bytes_string, offset)
        return contents_size

    def unpack(self, bytes_string, offset=0, previous_values={}):
        """Unpack bytes into Python objects

        :param bytes_string: packed data
        :param previous_values: previous packed values (optional)
        """
        # Get the contents header
        start_offset = offset

        offset += self._read_contents(bytes_string, offset)
        content_values = list(self.content_bits)

        has_none_types = content_values[self.NONE_CONTENT_INDEX]
        has_booleans = self.total_booleans and content_values[self.BOOL_CONTENT_INDEX]

        # If there are NoneType values they will be first
        if has_none_types:
            offset += self._read_nonetype_values(bytes_string, offset)

        # Ensure that the NoneType values are cleared
        else:
            self.none_bits.clear()

        # Create list for faster successive iterations
        none_values = list(self.none_bits)

        unpacked_items = []

        # All values have an entry in the contents bitfield
        for included, value_none, (key, handler) in zip(content_values, none_values, self.non_bool_handlers):
            if not included:
                continue

            # If this is a NONE value
            if value_none:
                value = None

            else:
                previous_value = previous_values.get(key)
                if previous_value is not None and handler.supports_mutable_unpacking:
                    # If we can't merge use default unpack
                    value_size = handler.unpack_merge(previous_value, bytes_string, offset)
                    value = previous_value

                # Otherwise ask for a new value
                else:
                    value, value_size = handler.unpack_from(bytes_string, offset)

                # We have unpacked a value, so shift by its size
                offset += value_size

            unpacked_items.append((key, value))

        # If there are Boolean values included in the data
        if has_booleans:
            # Read data from Boolean bitfields
            offset += self.boolean_packer.unpack_merge(self.bool_bits, bytes_string, offset)

            found_booleans = content_values[self.total_none_booleans:]
            none_booleans = none_values[self.total_none_booleans:]

            boolean_info = zip(self.bool_bits, self.bool_args, found_booleans, none_booleans)

            # Yield included boolean values
            for (value, (key, _), found, none_value) in boolean_info:
                if found:
                    unpacked_items.append((key, None if none_value else value))

        bytes_read = offset - start_offset
        # TODO update API users to handle new returned arg
        return unpacked_items, bytes_read

    def pack(self, data):
        """Pack data into bytes

        :param data: data to be packed
        """
        content_bits = self.content_bits
        none_bits = self.none_bits

        # Reset NoneType and contents bitfields
        none_bits.clear()
        content_bits.clear()

        # Create data_values list
        data_values = []
        append_value = data_values.append

        # Iterate over non booleans
        for index, (key, handler) in self.enumerated_non_bool_handlers:
            if key not in data:
                continue

            value = data[key]

            if value is None:
                none_bits[index] = True

            else:
                append_value(handler.pack(value))

            # Mark attribute as included
            content_bits[index] = True

        # Any remaining data will be Boolean values
        total_none_booleans = self.total_none_booleans
        has_booleans = len(data_values) != len(data)

        if has_booleans:
            # Reset booleans bitmask
            boolean_bitmask = self.bool_bits
            boolean_bitmask.clear()

            index_shift = total_none_booleans
            for index, (key, _) in self.enumerated_bool_args:
                if key not in data:
                    continue

                # Account for shift due to previous data
                content_index = index_shift + index

                # Register as included
                value = data[key]

                # Either save None value
                if value is None:
                    none_bits[content_index] = True

                # Or save a boolean value
                else:
                    boolean_bitmask[index] = value

                content_bits[content_index] = True

            # Mark Boolean values as included
            append_value(self.boolean_packer.pack(boolean_bitmask))
            content_bits[self.BOOL_CONTENT_INDEX] = True

        # If NoneType values have been set, mark them as included
        if none_bits:
            none_value_bytes = self.contents_packer.pack(none_bits)
            data_values.insert(0, none_value_bytes)
            content_bits[self.NONE_CONTENT_INDEX] = True

        return self.contents_packer.pack(content_bits) + b''.join(data_values)