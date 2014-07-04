import unittest

from ..bitfield import BitField, CBitField, PyBitField
from ..descriptors import Attribute
from ..type_flag import TypeFlag
from ..handler_interfaces import get_handler
from ..native_handlers import *
from ..network_struct import Struct
from ..serialiser import *


__all__ = ["SerialiserTest", "run_tests"]


class SerialiserTest(unittest.TestCase):

    int_value_8bit = 178
    int_bytes_string8bit = b'\xb2'

    int_value_16bit = 41593
    int_bytes_string16bit = b'\xa2y'

    int_value_32bit = 1938475617
    int_bytes_string32bit = b's\x8a\xcaa'

    int_value_64bit = 12398745609812398176
    int_bytes_string64bit = b'\xac\x111p\xd5MP`'

    float_bytes = b'@\x90\x02\x00\x00\x00\x00\x00'
    float_value = 1024.5

    py_struct_bytes = b'\x00\x14\x07\nTestStruct@@\x00\x00@\x00\x00\x00'
    c_struct_bytes = b'\x00\x14\xe0\nTestStruct@@\x00\x00@\x00\x00\x00'

    bitfield_list = [False, True, False, True, False, True, True, False]
    py_bitfield_fixed_value = b'j'
    py_bitfield_variable_value = b'\x08j'

    bool_value = True
    bool_bytes = b'\x01'

    def create_struct(self):
        class StructSample(Struct):
            x = Attribute(0.0)
            y = Attribute(0.0)
            name = Attribute(type_of=str)

        s = StructSample()
        s.x = 3.0
        s.y = 2.0
        s.name = "TestStruct"
        return s

    def test_get_struct(self):
        class StructSample(Struct):
            pass

        struct_flag = TypeFlag(StructSample)
        handler_struct = get_handler(struct_flag)
        self.assertIsInstance(handler_struct, StructHandler)

    def test_get_bitfield(self):
        bitfield_flag = TypeFlag(BitField)
        handler_bitfield = get_handler(bitfield_flag)

        self.assertIsInstance(handler_bitfield, BitFieldHandler)

    def test_get_float_low_precision(self):
        # Low precisions
        float_flag = TypeFlag(float, max_precision=False)
        handler_float = get_handler(float_flag)

        self.assertIs(handler_float, Float32)

    def test_get_float_high_precision(self):
        # High precisions
        float_flag = TypeFlag(float, max_precision=True)
        handler_float = get_handler(float_flag)

        self.assertIs(handler_float, Float64)

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

    def test_pack_struct(self):
        struct = self.create_struct()
        handler = StructHandler(TypeFlag(type(struct)))

        if BitField is PyBitField:
            struct_bytes = self.py_struct_bytes

        else:
            struct_bytes = self.c_struct_bytes

        self.assertEqual(struct_bytes, handler.pack(struct))

    def test_unpack_struct(self):
        struct = self.create_struct()
        handler = StructHandler(TypeFlag(type(struct)))

        if BitField is PyBitField:
            struct_bytes = self.py_struct_bytes

        else:
            struct_bytes = self.c_struct_bytes

        new_struct, struct_size = handler.unpack_from(struct_bytes)

        self.assertAlmostEqual(struct.x, new_struct.x)
        self.assertAlmostEqual(struct.y, new_struct.y)
        self.assertEqual(struct.name, new_struct.name)

    def test_pack_fixed_py_bitfield(self):
        # Get fixed handler
        size = len(self.bitfield_list)

        bitfield_flag = TypeFlag(BitField, fields=size)
        bitfield_handler = get_handler(bitfield_flag)

        # Create bitfield
        bitfield = PyBitField(size)
        bitfield[:] = self.bitfield_list

        packed_value = bitfield_handler.pack(bitfield)
        self.assertEqual(packed_value, self.py_bitfield_fixed_value)

    def test_pack_py_variable_bitfield(self):
        # Get variable handler
        bitfield_flag = TypeFlag(BitField)
        bitfield_handler = get_handler(bitfield_flag)

        # Create bitfield
        bitfield = PyBitField(8)
        bitfield[:] = self.bitfield_list

        packed_value = bitfield_handler.pack(bitfield)
        self.assertEqual(packed_value, self.py_bitfield_variable_value)

    def test_pack_int_64bit(self):
        self.assertEqual(UInt64.pack(self.int_value_64bit), self.int_bytes_string64bit)

    def test_pack_int_32bit(self):
        self.assertEqual(UInt32.pack(self.int_value_32bit), self.int_bytes_string32bit)

    def test_pack_int_16bit(self):
        self.assertEqual(UInt16.pack(self.int_value_16bit), self.int_bytes_string16bit)

    def test_pack_int_8bit(self):
        self.assertEqual(UInt8.pack(self.int_value_8bit), self.int_bytes_string8bit)

    def test_unpack_int_64bit(self):
        self.assertEqual(UInt64.unpack_from(self.int_bytes_string64bit)[0], self.int_value_64bit)

    def test_unpack_int_32bit(self):
        self.assertEqual(UInt32.unpack_from(self.int_bytes_string32bit)[0], self.int_value_32bit)

    def test_unpack_int_16bit(self):
        self.assertEqual(UInt16.unpack_from(self.int_bytes_string16bit)[0], self.int_value_16bit)

    def test_unpack_int_8bit(self):
        self.assertEqual(UInt8.unpack_from(self.int_bytes_string8bit)[0],self.int_value_8bit)

    def test_pack_float(self):
        self.assertEqual(Float64.pack(self.float_value), self.float_bytes)

    def test_unpack_float(self):
        self.assertEqual(Float64.unpack_from(self.float_bytes)[0], self.float_value)

    def test_pack_bool(self):
        self.assertEqual(BoolHandler.pack(self.bool_value), self.bool_bytes)

    def test_unpack_bool(self):
        self.assertEqual(BoolHandler.unpack_from(self.bool_bytes)[0], self.bool_value)


def run_tests():
    unittest.main(module="network.testing", exit=False)
