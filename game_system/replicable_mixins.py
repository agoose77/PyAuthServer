__all__ = ['IActorMixin']


class IActorMixin:

    @property
    def is_colliding(self):
        raise NotImplementedError()

    def colliding_with(self, other):
        raise NotImplementedError()
