from .bitfield import BitField
from .handler_interfaces import get_handler
from .descriptors import TypeFlag

__all__ = ["FlagSerialiser"]


class FlagSerialiser:
    """Interface class for parsing/dumping data to bytes
    Packed structure:
    [Contents, Data, Booleans, Nones]"""

    # The last two entries of the contents mask 
    NONE_CONTENT_INDEX = -1
    BOOL_CONTENT_INDEX = -2

    def __init__(self, arguments):
        '''Accepts ordered dict as argument'''
        self.bool_args = [(key, value) for key, value in arguments.items()
                          if value.type is bool]
        self.non_bool_args = [(key, value) for key, value in arguments.items()
                              if value.type is not bool]
        self.non_bool_handlers = [(key, get_handler(value))
                               for key, value in self.non_bool_args]

        # Maintain count of data types
        self.total_none_booleans = len(self.non_bool_args)
        self.total_booleans = len(self.bool_args)
        self.total_contents = self.total_none_booleans + self.total_booleans

        # BitFields used for packing
        self.bool_bits = BitField(self.total_booleans)
        self.none_bits = BitField(self.total_contents)

        # Additional two bits when including NoneType and Boolean values
        self.content_bits = BitField(self.total_contents + 2)
        self.bitfield_packer = get_handler(TypeFlag(BitField))

    def report_information(self, bytes_):
        bitfield_packer = self.bitfield_packer
        content_bits = bitfield_packer.unpack_from(bytes_)[:]
        content_data = bytes_[:bitfield_packer.size(bytes_)]
        print("Contents", content_data)
        bytes_ = bytes_[bitfield_packer.size(bytes_):]
        entry_names = [i[0] for i in self.non_bool_args + self.bool_args]

        # If there are NoneType values they will be first
        if content_bits[self.NONE_CONTENT_INDEX]:
            none_bits = bitfield_packer.unpack_from(bytes_)
            none_data = bytes_[:bitfield_packer.size(bytes_)]
            print("None values", none_data)
            bytes_ = bytes_[bitfield_packer.size(bytes_):]

        else:
            none_bits = [False] * self.total_contents
            none_data = None

        is_bool = [i[0] for i in self.bool_args].__contains__
        for name, included, is_none in zip(entry_names, content_bits, none_bits):
            if not included:
                continue

            print("{} : {}".format(name, "None" if is_none else ("Bool" if is_bool(name) else "Default")))

        print()

    def unpack(self, bytes_, previous_values={}):
        '''Accepts ordered bytes, and optional previous values'''
        bitfield_packer = self.bitfield_packer
        bitfield_packer.unpack_merge(self.content_bits, bytes_)
        bytes_ = bytes_[bitfield_packer.size(bytes_):]
        content_values = list(self.content_bits)

        # If there are NoneType values they will be first
        if content_values[self.NONE_CONTENT_INDEX]:
            bitfield_packer.unpack_merge(self.none_bits, bytes_)
            bytes_ = bytes_[bitfield_packer.size(bytes_):]

        # Ensure that the NoneType values are cleared
        else:
            self.none_bits.clear()

        # All values have an entry in the contents bitfield
        for included, value_none, (key, handler) in zip(content_values,
                                                        self.none_bits,
                                                        self.non_bool_handlers):
            if not included:
                continue

            # If this is a NONE value
            if value_none:
                yield (key, None)
                continue

            # If the value can be merged with an existing data type
            if key in previous_values and hasattr(handler, "unpack_merge"):
                value = previous_values[key]
                # If we can't merge use default unpack
                if value is None:
                    value = handler.unpack_from(bytes_)

                else:
                    handler.unpack_merge(value, bytes_)

            # Otherwise ask for a new value
            else:
                value = handler.unpack_from(bytes_)

            yield (key, value)

            bytes_ = bytes_[handler.size(bytes_):]

        # If there are Boolean values included in the data
        if self.total_booleans and content_values[self.BOOL_CONTENT_INDEX]:
            # Read data from Boolean bitfields
            bitfield_packer.unpack_merge(self.bool_bits, bytes_)
            boolean_data = zip(self.bool_bits, self.bool_args,
                               content_values[self.total_none_booleans:],
                               self.none_bits[self.total_none_booleans:])

            # Iterate over Boolean values
            for bool_value, (key, _), included, is_none in boolean_data:
                # Only send if included
                if included:
                    yield (key, None if is_none else bool_value)

    def pack(self, data):
        content_bits = self.content_bits
        none_bits = self.none_bits

        # Reset NoneType and contents Bitmasks
        none_bits.clear()
        content_bits.clear()

        # Create data_values list
        data_values = []
        append_value = data_values.append

        # Iterate over non booleans
        for index, (key, handler) in enumerate(self.non_bool_handlers):
            if not key in data:
                continue

            # Register as included
            content_bits[index] = True
            value = data.pop(key)
            if value is None:
                none_bits[index] = True

            else:
                append_value(handler.pack(value))

        # Any remaining data will be Boolean values
        if data:
            # Reset bool mask
            bools = self.bool_bits
            bools.clear()

            index_shift = self.total_none_booleans
            for index, (key, _) in enumerate(self.bool_args):
                if not key in data:
                    continue

                # Account for shift due to previous data
                content_index = index_shift + index

                # Register as included
                content_bits[content_index] = True
                value = data[key]

                # Either save None value
                if value is None:
                    none_bits[content_index] = True

                # Or save a boolean value
                else:
                    bools[index] = value

            # Mark Boolean values as included
            content_bits[self.BOOL_CONTENT_INDEX] = True
            append_value(self.bitfield_packer.pack(bools))

        # If NoneType values have been set, mark them as included
        if none_bits:
            content_bits[self.NONE_CONTENT_INDEX] = True
            data_values.insert(0, self.bitfield_packer.pack(none_bits))

        return self.bitfield_packer.pack(content_bits) + b''.join(data_values)