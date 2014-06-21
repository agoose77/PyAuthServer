import _ctypes

__all__ = ["dereference_id"]


def dereference_id(id_):
    return _ctypes.PyObj_FromPtr(id_)