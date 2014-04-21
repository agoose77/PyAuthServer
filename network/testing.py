import unittest

from .bitfield import BitField
from .descriptors import TypeFlag
from .handler_interfaces import get_handler
from .native_handlers import *
from .serialiser import *


class SerialiserTest(unittest.TestCase):

    int_value_8bit = 178
    int_bytes_8bit = b'\xb2'

    int_value_16bit = 41593
    int_bytes_16bit = b'\xa2y'

    int_value_32bit = 1938475617
    int_bytes_32bit = b's\x8a\xcaa'

    int_value_64bit = 12398745609812398176
    int_bytes_64bit = b'\xac\x111p\xd5MP`'

    float_bytes = b'@\x90\x02\x00\x00\x00\x00\x00'
    float_value = 1024.5

    bitfield_list = [False, True, False, True, False, True, True, False]
    bitfield_fixed_value = b'j'
    bitfield_variable_value = b'\x08j'

    def test_get_fixed_bitfield(self):
        bitfield_flag = TypeFlag(BitField, fields=len(self.bitfield_list))
        handler_bitfield = get_handler(bitfield_flag)

        self.assertIsInstance(handler_bitfield, FixedBitFieldHandler)

    def test_get_variable_bitfield(self):
        bitfield_flag = TypeFlag(BitField)
        handler_bitfield = get_handler(bitfield_flag)

        self.assertIs(handler_bitfield, VariableBitFieldHandler)

    def test_get_float_low_precision(self):
        # Low precisions
        float_flag = TypeFlag(float, max_precision=False)
        handler_float = get_handler(float_flag)

        self.assertIs(handler_float, Float4)

    def test_get_float_high_precision(self):
        # High precisions
        float_flag = TypeFlag(float, max_precision=True)
        handler_float = get_handler(float_flag)

        self.assertIs(handler_float, Float8)

    def test_get_int_8bit(self):
        int_flag = TypeFlag(int, max_bits=8)
        handler_int = get_handler(int_flag)

        self.assertIs(handler_int, UInt8)

    def test_get_int_16bit(self):
        int_flag = TypeFlag(int, max_bits=16)
        handler_int = get_handler(int_flag)

        self.assertIs(handler_int, UInt16)

    def test_get_int_32bit(self):
        int_flag = TypeFlag(int, max_bits=32)
        handler_int = get_handler(int_flag)

        self.assertIs(handler_int, UInt32)

    def test_get_int_64bit(self):
        int_flag = TypeFlag(int, max_bits=64)
        handler_int = get_handler(int_flag)

        self.assertIs(handler_int, UInt64)

    def test_pack_fixed_bitfield(self):
        # Get fixed handler
        bitfield_handler = FixedBitFieldHandler

        # Create bitfield
        size = len(self.bitfield_list)
        bitfield = BitField(size)
        bitfield[:] = self.bitfield_list

        packed_value = bitfield_handler(size).pack(bitfield)
        self.assertEqual(packed_value, self.bitfield_fixed_value)

    def test_pack_variable_bitfield(self):
        # Get fixed handler
        bitfield_handler = VariableBitFieldHandler

        # Create bitfield
        bitfield = BitField(8)
        bitfield[:] = self.bitfield_list

        packed_value = bitfield_handler.pack(bitfield)
        self.assertEqual(packed_value, self.bitfield_variable_value)

    def test_pack_int_64bit(self):
        self.assertEqual(UInt64.pack(self.int_value_64bit),
                         self.int_bytes_64bit)

    def test_pack_int_32bit(self):
        self.assertEqual(UInt32.pack(self.int_value_32bit),
                         self.int_bytes_32bit)

    def test_pack_int_16bit(self):
        self.assertEqual(UInt16.pack(self.int_value_16bit),
                         self.int_bytes_16bit)

    def test_pack_int_8bit(self):
        self.assertEqual(UInt8.pack(self.int_value_8bit),
                         self.int_bytes_8bit)

    def test_unpack_int_64bit(self):
        self.assertEqual(UInt64.unpack(self.int_bytes_64bit),
                         self.int_value_64bit)

    def test_unpack_int_32bit(self):
        self.assertEqual(UInt32.unpack(self.int_bytes_32bit),
                         self.int_value_32bit)

    def test_unpack_int_16bit(self):
        self.assertEqual(UInt16.unpack(self.int_bytes_16bit),
                         self.int_value_16bit)

    def test_unpack_int_8bit(self):
        self.assertEqual(UInt8.unpack(self.int_bytes_8bit),
                         self.int_value_8bit)

    def test_pack_float(self):
        self.assertEqual(Float8.pack(self.float_value),
                         self.float_bytes)

    def test_unpack_float(self):
        self.assertEqual(Float8.unpack(self.float_bytes),
                         self.float_value)


def main():
    unittest.main(module="network.testing", exit=False)
