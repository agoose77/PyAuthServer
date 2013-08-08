'''
Created on 29 Jul 2013

@author: Angus
'''

from .bitfield import Bitfield
from .handler_interfaces import get_handler
from .descriptors import StaticValue

class ArgumentSerialiser:
    
    def __init__(self, arguments):
        '''Accepts ordered dict as argument'''        
        self.bools = [(name, value) for name, value in arguments.items() if value.type is bool]
        self.others = [(name, value) for name, value in arguments.items() if value.type is not bool]
        self.handlers = [(name, get_handler(value)) for name, value in self.others]
        
        self.total_normal = len(self.others)
        self.total_bools = len(self.bools)
        self.total_contents = self.total_normal + bool(self.total_bools)
        
        # Bitfields used for packing, Boolean packing necessitates storing previous values
        self.content_bits = Bitfield(size=self.total_contents)
        self.bool_bits = Bitfield(size=self.total_bools)
        
        self.bitfield_packer = get_handler(StaticValue(Bitfield))
        
    def unpack(self, bytes_, previous_values={}):
        '''Accepts ordered bytes, and optional previous values'''
        self.bitfield_packer.unpack_merge(self.content_bits, bytes_)
        bytes_ = bytes_[self.content_bits.footprint:]
        
        contents = list(self.content_bits)
        
        for included, (key, handler) in zip(contents, self.handlers):
            if not included:
                continue
            
            # If the value can be merged with an existing value
            if key in previous_values and hasattr(handler, "unpack_merge"):
                value = previous_values[key]
                
                if value is None:
                    value = handler.unpack_from(bytes_)
                else:
                    handler.unpack_merge(value, bytes_)
                    
            else:
                value = handler.unpack_from(bytes_)
                
            yield (key, value)
            
            bytes_ = bytes_[handler.size(bytes_):]
        
        # If we have boolean values and they're included
        if self.bool_bits and contents[-1]:
            self.bitfield_packer.unpack_merge(self.bool_bits, bytes_)        
            for value, (key, static_value) in zip(self.bool_bits, self.bools):
                yield (key, value)

    def pack(self, data, current_values={}):
        # Reset content mask
        contents = self.content_bits
        
        contents.clear()
        
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
            bools.clear()
            
            # Iterate over booleans
            for index, (key, static_value) in enumerate(self.bools):
                if not key in data:
                    continue
                
                bools[index] = data[key]
                
            contents[-1] = True
            output.append(self.bitfield_packer.pack(bools))
      
        return self.bitfield_packer.pack(contents) + b''.join(output)