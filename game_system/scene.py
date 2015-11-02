from network.scene import Scene as _Scene

from .entity import Actor
from .resources import ResourceManager
from .timer import Timer
from .physics import create_network_physics_manager


class Scene(_Scene):

    def __init__(self, world, name):
        super().__init__(world, name)

        self.timers = []

        self.resource_manager = ResourceManager(world.root_filepath)
        self.network_physics_manager = create_network_physics_manager(world)

        self.messenger.add_subscriber("replicable_created", self._on_replicable_created)
        self.messenger.add_subscriber("replicable_removed", self._on_replicable_destroyed)

    def add_timer(self, delay, repeat=False):
        """Create timer object

        :param delay: delay until timer is finished
        :param repeat: prevents timer from expiring
        """
        timer = Timer(delay, repeat)
        self.timers.append(timer)
        return timer

    def remove_timer(self, timer):
        self.timers.remove(timer)

    def tick(self):
        super().tick()

        self._update_timers()
        self.network_physics_manager.tick()

    def _on_replicable_created(self, replicable):
        if isinstance(replicable, Actor):
            self.network_physics_manager.add_actor(replicable)

    def _on_replicable_destroyed(self, replicable):
        if isinstance(replicable, Actor):
            self.network_physics_manager.remove_actor(replicable)

    def _update_timers(self):
        """Update Timer objects"""
        dt = 1 / self.world.tick_rate

        finished_timers = set()

        for timer in self.timers:
            is_finished = timer.update(dt)

            if is_finished:
                finished_timers.add(timer)

        for timer in finished_timers:
            self.remove_timer(timer)