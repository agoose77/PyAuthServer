"""Network library to enable simple networking between Python objects.
Supports native replication of many Python built in types
Extendable for new data types
"""
# TODO listen server support

import os

if os.getenv("NETWORK_DO_TESTING"):
    from .testing import run_tests

    run_tests()
    
from . import native_handlers as _