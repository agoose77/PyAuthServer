from copy import deepcopy
from collections import deque


class BoundContextManager:

    def __init__(self, cls, name):
        self.name = name

        self._cls = cls
        self._context = {}
        self._depth = 0
        self._previous_context = None

    def __enter__(self):
        if self._depth:
            return

        cls = self._cls

        self._previous_context = cls._context_data
        cls._context_data = self._context

        cls._context_stack.append(self.name)
        self._depth += 1

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._depth > 1:
            return

        cls = self._cls

        cls._context_stack.pop()
        cls._context_data = self._previous_context

    def __repr__(self):
        return "{}::{{{}}}".format(self._cls.__name__, self.name)


class GlobalDataContext(type):
    """ContextMember instances attributed to members of the class tree of GlobalDataContext (metaclasses, derived classes)
    will be dependent upon a global context
    """

    def __new__(metacls, name, bases, attrs):
        cls = super().__new__(metacls, name, bases, attrs)

        if not hasattr(cls, "_context_data"):
            cls._context_data = cls.get_default_context()
            cls._context_stack = deque(("<DEFAULT>",))

        return cls

    @property
    def qualified_context(cls):
        return ".".join(cls._context_stack)

    def get_default_context(cls):
        return {}

    def replace_context(cls, context):
        old_context = cls._context_data
        cls._context_data = context
        return old_context

    def get_context_manager(cls, name="Context"):
        return BoundContextManager(cls, name)
    

class ContextMember:
    """Data attribute used with GlobalDataContext to store contextually global data"""

    def __init__(self, default):
        self.default = default
    
    def __get__(self, instance, cls):
        if instance is None:
            return self

        try:
            return instance._context_data[self]
        
        except KeyError:
            new_value = self.factory(instance)
            instance._context_data[self] = new_value
            return new_value

    def __set__(self, instance, value):
        try:
            instance._context_data[self] = value

        except AttributeError:
            raise

    def factory(self, instance):
        return deepcopy(self.default)