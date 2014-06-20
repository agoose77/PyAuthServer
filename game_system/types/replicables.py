__all__ = ['IActorMixin', 'ICameraActorMixin', 'ILampMixin', 'INavmeshMixin']


class IActorMixin:

    @property
    def is_colliding(self):
        raise NotImplementedError()

    def colliding_with(self, other):
        raise NotImplementedError()

    @UpdateCollidersSignal.global_listener
    def _update_colliders(self):
        raise NotImplementedError()


class ICameraMixin:
    """Base class for Camera"""

    @contextmanager
    def active_context(self):
        raise NotImplementedError()


class ILampMixin:

    @property
    def intensity(self):
        raise NotImplementedError()

    @intensity.setter
    def intensity(self, energy):
        raise NotImplementedError()


class INavmeshMixin:

    def draw(self):
        raise NotImplementedError()

    def find_path(self, from_point, to_point):
        raise NotImplementedError()

    def get_wall_intersection(self, from_point, to_point):
        raise NotImplementedError()