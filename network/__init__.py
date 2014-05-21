"""Network library to enable simple networking between Python objects.
Supports native replication of many Python built in types
Extendable for new data types
"""

from .bitfield import *
from .serialiser import *
from .channel import *
from .conditions import *
from .connection import *
from .connection_interfaces import *
from .containers import *
from .conversions import *
from .decorators import *
from .descriptors import *
from .enums import *
from .errors import *
from .flag_serialiser import *
from .handler_interfaces import *
from .iterators import *
from .instance_register import *
from .logger import *
from .native_handlers import *
from .network import *
from .netmode_switch import *
from .network_struct import *
from .packet import *
from .profiler import *
from .replicable_register import *
from .replicable import *
from .world_info import *
from .replication_rules import *
from .rpc import *
from .signals import *
from .structures import *
from .type_register import *
from .testing import *

run_tests()