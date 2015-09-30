"""Provides interfaces to serialise native types to bytes"""

USE_NUMPY = False

if USE_NUMPY:
    from .numpy_serialiser import *

else:
    from .serialiser import *