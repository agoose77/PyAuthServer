from .metaclasses.context import AggregateContext
from .connection import Connection
from .scene import NetworkScene
from .annotations.decorators import set_netmode_getter

from contextlib import contextmanager


class World:

    current_world = None

    def __init__(self, netmode):
        self._netmode = netmode

        scene_context = NetworkScene.create_context_manager()
        connection_context = Connection.create_context_manager()
        set_current_world = self._set_current_world(self)
        self._context = AggregateContext(scene_context, set_current_world, connection_context)

    def __enter__(self):
        return self._context.__enter__()

    def __exit__(self, *exc_args):
        self._context.__exit__(*exc_args)

    @property
    def netmode(self):
        return self._netmode

    @property
    def scenes(self):
        return list(NetworkScene)

    @contextmanager
    def _set_current_world(self, world):
        """When using this world, set the current world for the class"""
        cls = self.__class__

        old_world = cls.current_world
        cls.current_world = world
        yield
        cls.current_world = old_world


# Global access to current netmode
def get_current_netmode():
    return World.current_world.netmode


set_netmode_getter(get_current_netmode)
