from collections import deque


class BoundContextManager:
    """Context manager for ContextMemberMeta objects
    """

    def __init__(self, cls, name):
        self.name = name

        self._cls = cls
        self._context = cls.get_default_context()
        self._depth = 0
        self._previous_context = None

    def __enter__(self):
        if self._depth:
            return

        cls = self._cls

        self._previous_context = cls.get_context()
        cls.set_context(self._context)

        cls.context_stack.append(self.name)
        self._depth += 1

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._depth > 1:
            return

        cls = self._cls
        cls.context_stack.pop()
        cls.set_context(self._previous_context)

    def __repr__(self):
        return "{}::{{{}}}".format(self._cls.__name__, self.name)


class ContextMemberMeta(type):
    """ContextMember instances attributed to members of the class tree of GlobalDataContext (metaclasses, derived classes)
    will be dependent upon a global context
    """

    def __new__(metacls, name, bases, attrs):
        cls = super().__new__(metacls, name, bases, attrs)

        if not hasattr(cls, "context_data"):
            cls.context_data = {}
            cls.context_stack = deque(("<DEFAULT>",))

        return cls

    @property
    def qualified_context(cls):
        return ".".join(cls.context_stack)

    def get_context_manager(cls, name="Context"):
        return BoundContextManager(cls, name)

    def get_context(cls):
        """Get description of current context data for this class.

        This data may be in a different format to that of _context_data
        """
        return cls.context_data

    def get_default_context(cls):
        return {}

    def set_context(cls, context):
        """Set current context data for this class from previous description"""
        cls.context_data = context