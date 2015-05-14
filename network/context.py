from contextlib import contextmanager
from copy import deepcopy
from collections import deque


class GlobalDataContext(type):
    """ContextMember instances attributed to members of the class tree of GlobalDataContext (metaclasses, derived classes)
    will be dependent upon a global context
    """
    _context_data = {}
    _context_stack = deque(("<DEFAULT>",))

    @property
    def qualified_context(cls):
        return ".".join(cls._context_stack)

    def get_context(cls, name="Context"):
        context_dict = {}
        context_stack = cls._context_stack

        @contextmanager
        def context():
            previous_context = cls._context_data
            if previous_context is context_dict:
                yield

            else:
                cls._context_data = context_dict
                context_stack.append(name)
                yield
                context_stack.pop()
                cls._context_data = previous_context

        context.__qualname__ = "{}::{{{}}}".format(cls.__name__, name)
        return context
    

class ContextMember:
    """Data attribute used with GlobalDataContext to store contextually global data"""

    def __init__(self, default):
        self.default = default
    
    def __get__(self, instance, cls):
        try:
            return instance._context_data[self]
        
        except KeyError:
            new_value = self.factory(instance)
            instance._context_data[self] = new_value
            return new_value
        
    def __set__(self, instance, value):
        instance._context_data[self] = value

    def factory(self, instance):
        return deepcopy(self.default)