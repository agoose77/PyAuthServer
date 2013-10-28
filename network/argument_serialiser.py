from .bitfield import Bitfield
from .handler_interfaces import get_handler
from .descriptors import StaticValue


class ArgumentSerialiser:
    """Serialiser class for parsing/dumping data to bytes"""
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

        self.bitfield_packer.unpack_merge(self.content_bits, bytes_)
        bytes_ = bytes_[self.bitfield_packer.size(bytes_):]
        content_values = list(self.content_bits)

        # If there are None values
        if content_values[-1]:
            self.bitfield_packer.unpack_merge(self.none_bits, bytes_)
        
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
            self.bitfield_packer.unpack_merge(self.bool_bits, bytes_)
            for bool_value, (key, static_value) in zip(self.bool_bits,
                                                       self.bools):
                yield (key, bool_value)

    def pack(self, data, current_values={}):
        contents = self.content_bits
        none_values = self.none_bits

        # Reset none data and contents mask
        none_values.clear()
        contents.clear()

        # Create data_values list
        data_values = []

        # Iterate over non booleans
        for index, (key, handler) in enumerate(self.handlers):

            if not key in data:
                continue

            contents[index] = True
            value = data.pop(key)

            if value is None:
                none_values[index] = True

            else:
                data_values.append(handler.pack(value))

        # If we have boolean values remaining
        if data:
            # Reset bool mask
            bools = self.bool_bits
            bools.clear()

            # Iterate over booleans
            for index, (key, static_value) in enumerate(self.bools):
                if not key in data:
                    continue

                bools[index] = data[key]

            contents[-2] = True

            data_values.append(self.bitfield_packer.pack(bools))

        # If we have values set to None
        if none_values:
            contents[-1] = True
            data_values.append(self.bitfield_packer.pack(none_values))

        return self.bitfield_packer.pack(contents) + b''.join(data_values)
