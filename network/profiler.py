from cProfile import Profile
from collections import defaultdict
from functools import wraps
from pstats import Stats

__all__ = ['ProfileManager', "ContextProfile", 'profiler']


class ContextProfile(Profile):
    """Profile class which implements the context manager protocol"""

    def __enter__(self):
        self.enable()

    def __exit__(self, type, value, traceback):
        self.disable()


class ProfileManager:
    """Profiling interface class"""

    def __init__(self):
        self._profiles = defaultdict(ContextProfile)

    def decorate(self, func):
        """Profile decorated function

        :param func: decorated function
        """
        func_name = func.__qualname__
        profile = self._profiles[func_name]

        @wraps(func)
        def wrapper(*args, **kwargs):
            with profile:
                func(*args, **kwargs)

        return wrapper

    def get_stats(self):
        """Create dictionary of profile name: Stats object for each profile"""
        return {profile_name: Stats(profile) for profile_name, profile in self._profiles.items()}


profiler = ProfileManager()
