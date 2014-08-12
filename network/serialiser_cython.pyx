from cpython.array cimport array, clone
from libc.string cimport memcmp, memcpy
from libc.math cimport frexp, ldexp
from libc.stdint cimport int32_t, int64_t


ctypedef fused integer:
    int32_t
    int64_t


cdef enum float_format_type:
    unknown_format,
    ieee_big_endian_format,
    ieee_little_endian_format


cdef array stringtemplate = array('B')
cdef float_format_type double_format



cdef double x = 9006104071832581.0

big_endian = b"\x43\x3f\xff\x01\x02\x03\x04\x05"
little_endian = bytes(reversed(big_endian))

if sizeof(double) == 8:
    if memcmp(&x, big_endian, 8) == 0:
        double_format = ieee_big_endian_format
    elif memcmp(&x, little_endian, 8) == 0:
        double_format = ieee_little_endian_format
    else:
        double_format = unknown_format

else:
    double_format = unknown_format


cdef void _write_integer(integer x, char* output):
    cdef int i
    for i in range(sizeof(integer)-1, -1, -1):
        output[i] = <char>x
        x >>= 8


cpdef bytes write_int(int32_t i):
    cdef array output = clone(stringtemplate, sizeof(int32_t), False)
    _write_integer(i, output.data.as_chars)
    return output.data.as_chars[:sizeof(int32_t)]


cpdef bytes write_long(int64_t i):
    cdef array output = clone(stringtemplate, sizeof(int64_t), False)
    _write_integer(i, output.data.as_chars)
    return output.data.as_chars[:sizeof(int64_t)]



cdef class Int32:
    cdef int size = 4


#pack
#unpack
#packmultiple
#unpackmultiple`
