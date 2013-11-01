from .bitfield import Bitfield
from .handler_interfaces import get_handler
from .descriptors import StaticValue


class ArgumentSerialiser:
    """Serialiser class for parsing/dumping data to bytes
    Packed structure:
    Contents, Data, Booleans, Nones"""

    def __init__(self, arguments):
        '''Accepts ordered dict as argument'''
        self.bools = [(key, value) for key, value in arguments.items()
                      if value.type is bool]
        self.others = [(key, value) for key, value in arguments.items()
                       if value.type is not bool]
        self.handlers = [(key, get_handler(value)) for key, value
                         in self.others]

        self.total_normal = len(self.others)
        self.total_bools = len(self.bools)
        self.total_contents = self.total_normal + bool(self.total_bools)

        # Bitfields used for packing
        # Boolean packing necessitates storing previous values
        self.content_bits = Bitfield(size=self.total_contents + 1)
        self.bool_bits = Bitfield(size=self.total_bools)
        self.none_bits = Bitfield(size=self.total_contents)

        self.bitfield_packer = get_handler(StaticValue(Bitfield))

    def unpack(self, bytes_, previous_values={}):
        '''Accepts ordered bytes, and optional previous values'''
        bitfield_packer = self.bitfield_packer
        bitfield_packer.unpack_merge(self.content_bits, bytes_)

        bytes_ = bytes_[bitfield_packer.size(bytes_):]
        content_values = list(self.content_bits)

        # If there are None values
        if content_values[-1]:
            bitfield_packer.unpack_merge(self.none_bits, bytes_)

        for included, value_none, (key, handler) in zip(content_values,
                                                     self.none_bits,
                                                     self.handlers):

            if not included:
                continue

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

        # If there are Boolean values
        if self.total_bools and content_values[-2]:
            bitfield_packer.unpack_merge(self.bool_bits, bytes_)
            for bool_value, (key, static_value) in zip(self.bool_bits,
                                                       self.bools):
                yield (key, bool_value)

    def pack(self, data, current_values={}):
        content_bits = self.content_bits
        none_bits = self.none_bits

        # Reset none data and content_bits mask
        none_bits.clear()
        content_bits.clear()

        # Create data_values list
        data_values = []

        # Iterate over non booleans
        for index, (key, handler) in enumerate(self.handlers):

            if not key in data:
                continue

            content_bits[index] = True
            value = data.pop(key)

            if value is None:
                none_bits[index] = True

            else:
                data_values.append(handler.pack(value))

        # Remaining data MUST be booleans
        if data:
            # Reset bool mask
            bools = self.bool_bits
            bools.clear()

            # Iterate over booleans
            for index, (key, static_value) in enumerate(self.bools):
                if not key in data:
                    continue

                bools[index] = data[key]

            content_bits[-2] = True

            data_values.append(self.bitfield_packer.pack(bools))

        # If we have values set to None
        if none_bits:
            content_bits[-1] = True
            data_values.append(self.bitfield_packer.pack(none_bits))

        return self.bitfield_packer.pack(content_bits) + b''.join(data_values)
