"""Network library to enable simple networking between Python objects.
Supports native replication of many Python built in types
Extendable for new data types
"""

NUMPY_SERIALISER = False
# TODO listen server support

from .bitfield import *
from .serialiser import *
if NUMPY_SERIALISER:
    from .numpy_serialiser import *
from .channel import *
from .conditions import *
from . import streams
from . import metaclasses
from .connection import *
from .containers import *
from .conversions import *
from .decorators import *
from .descriptors import *
from .enums import *
from .errors import *
from .flag_serialiser import *
from .handler_interfaces import *
from .hosts import *
from .iterators import *
from .logger import *
from .native_handlers import *
from .network import *
from .tagged_delegate import *
from .network_struct import *
from .packet import *
from .profiler import *
from .replicable import *
from .world_info import *
from .replication_rules import *
from .rpc import *
from .signals import *
from .simple_network import *
from .structures import *
from .testing import *

run_tests()