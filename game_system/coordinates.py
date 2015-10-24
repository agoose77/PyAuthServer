try:
    from mathutils import *

except ImportError:
    try:
        from ._mathutils import *
    except ImportError as err:
        raise ImportError("Unable to import mathutils library") from err
