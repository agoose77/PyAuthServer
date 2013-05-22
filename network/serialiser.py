from struct import Struct
from mathutils import Vector

class IStruct(Struct):
    def size(self, bytes_=None):
        return super().size
    
    def unpack(self, bytes_):
        return super().unpack(bytes_)[0]
    
    def unpack_from(self, bytes_):
        return super().unpack_from(bytes_)[0]
    
UInt32 = IStruct("@I")
UInt16 = IStruct("@H")
UInt64 = IStruct("@L")
UInt8 = IStruct("@B")
Float4 = IStruct("@f")
Float8 = IStruct("@d")
    
class String:
    packer = UInt8
    
    @classmethod
    def pack(cls, str_):
        return cls.packer.pack(len(str_)) + str_.encode()
    
    @classmethod
    def unpack(cls, bytes_):
        return bytes_[1:].decode()
    
    @classmethod
    def size(cls, bytes_):
        length = cls.packer.unpack_from(bytes_)
        return length + 1
    
    @classmethod
    def unpack_from(cls, bytes_):
        length = cls.size(bytes_)
        return cls.unpack(bytes_[:length])

