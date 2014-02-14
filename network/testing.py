import unittest
from . import get_handler, TypeFlag, Float8, UInt32, UInt64


class SerialiserTest(unittest.TestCase):

    int_bytes = b'\xf4\xe2Y\xfbU.\xc7\x8a'
    int_value = 10000012444423545588

    float_bytes = b'\x00\x00\x00\x00\x00\x02\x90@'
    float_value = 1024.5

    def test_get_float(self):
        float_flag = TypeFlag(float, max_precision=True)
        handler_float = get_handler(float_flag)

        self.assertIs(handler_float, Float8)

    def test_get_int(self):
        int_flag = TypeFlag(int, max_value=(2 ** 32 - 1))
        handler_int = get_handler(int_flag)

        self.assertIs(handler_int, UInt32)

    def test_pack_int(self):
        self.assertEqual(UInt64.pack(self.int_value),
                         self.int_bytes)

    def test_pack_float(self):
        self.assertEqual(Float8.pack(self.float_value),
                         self.float_bytes)

    def test_unpack_int(self):
        self.assertEqual(UInt64.unpack(self.int_bytes),
                         self.int_value)

    def test_unpack_float(self):
        self.assertEqual(Float8.unpack(self.float_bytes),
                         self.float_value)


def main():
    unittest.main(module="network.testing", exit=False)
