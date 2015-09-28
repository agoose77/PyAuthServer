class InvalidContextDict:

    def __getitem__(self, item):
        raise RuntimeError("Cannot retrieve item from invalid context")

    def __setitem__(self, item, value):
        raise RuntimeError("Cannot set item on invalid context")


class InvalidContextManager:

    data = InvalidContextDict()

    def __enter__(self):
        raise RuntimeError("Cannot enter invalid context")

    def __exit__(self, exc_type, exc_val, exc_tb):
        raise RuntimeError("Cannot exit invalid context")

    def __repr__(self):
        return "Invalid Context"


class BoundContextManager:
    """Context manager for ContextMemberMeta objects"""

    def __init__(self, cls, name):
        self.name = name
        self.data = cls.get_default_context()

        self._cls = cls
        self._depth = 0
        self._previous_context_managers = []

    def __enter__(self):
        cls = self._cls

        self._previous_context_managers.append(cls.current_context_manager)
        cls.current_context_manager = self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._cls.current_context_manager = self._previous_context_managers.pop()

    def __repr__(self):
        return "{}::{{{}}}".format(self._cls.__name__, self.name)

    def merge(self, other):
        """Merge with other context"""
        return self._cls.merge_context(other)


class ContextMemberMeta(type):
    """ContextMember instances attributed to members of the class tree of GlobalDataContext
    (metaclasses, derived classes) will be dependent upon a global context
    """

    create_default_context = True

    def __new__(metacls, name, bases, attrs):
        cls = super().__new__(metacls, name, bases, attrs)

        if not hasattr(cls, "current_context_manager"):
            if cls.create_default_context:
                cls.current_context_manager = BoundContextManager(cls, "<DEFAULT>")

            else:
                cls.current_context_manager = InvalidContextManager()

        return cls

    @property
    def current_context_manager(cls):
        return cls._current_context_manager

    @current_context_manager.setter
    def current_context_manager(cls, context_manager):
        cls._current_context_manager = context_manager
        cls.context_member_data = context_manager.data

    def create_context_manager(cls, name="Context"):
        """Create a context manager which owns the contextual state for this class

        :param name: name of context manager
        """
        return BoundContextManager(cls, name)

    def get_default_context(cls):
        """Return default context data for this class, for new context managers"""
        return {}

    def merge_context(cls, context):
        """Merge other context with current context.

        Returns current context manager
        """
        current_context_manager = cls.current_context_manager
        current_context_manager.data.update(context.data)
        context.data.clear()
        return current_context_manager


class AggregateContext:

    def __init__(self, *contexts):
        self.contexts = contexts

    def __enter__(self):
        for context in self.contexts:
            context.__enter__()

    def __exit__(self, *exc_details):
        for context in self.contexts:
            context.__exit__(*exc_details)
