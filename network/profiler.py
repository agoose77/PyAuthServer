from cProfile import Profile
from collections import defaultdict

from .signals import ProfileSignal, SignalListener


class ProfileManager(SignalListener):
    def __init__(self):
        super().__init__()

        self._profiles = defaultdict(Profile)

        self.register_signals()

    @ProfileSignal.global_listener
    def update_profiler(self, profile_id, start):
        profile = self._profiles[profile_id]
        if start:
            profile.enable()
        else:
            profile.disable()
            profile.dump_stats("C:/{}.results".format(profile_id))

profiler = ProfileManager()
