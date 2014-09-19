"""Provides interfaces to serialise native types to bytes"""

USE_NUMPY = False

if USE_NUMPY:
    from .serialiser import *

else:
    from .numpy_serialiser import *