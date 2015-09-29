from .metaclasses.register import InstanceRegister
from .metaclasses.context import AggregateContext
from .descriptors import ContextMember
from .replicable import Replicable
from .signals import Signal, SceneRegisteredSignal, SceneUnregisteredSignal


class CurrentSceneContext:

    def __init__(self, scene):
        self.scene = scene
        self._current_scene = None

    def __enter__(self):
        cls = self.scene.__class__
        self._current_scene = cls.current_scene
        cls.current_scene = self.scene

    def __exit__(self, *exc_args):
        cls = self.scene.__class__
        cls.current_scene = self._current_scene
        self._current_scene = None


class NetworkScene(metaclass=InstanceRegister):

    current_scene = ContextMember(None)

    def __init__(self, name, *args, **kwargs):
        # Create context
        replicable_context = Replicable.create_context_manager(name)
        signal_context = Signal.create_context_manager(name)
        set_current_scene = CurrentSceneContext(self)
        self._context = AggregateContext(replicable_context, signal_context, set_current_scene)

        super().__init__(instance_id=name, *args, **kwargs)

    def __enter__(self):
        return self._context.__enter__()

    def __exit__(self, *exc_args):
        self._context.__exit__(*exc_args)

    def __repr__(self):
        return "<NetworkScene '{}'>".format(self.name)

    @classmethod
    def create_or_return(cls, instance_id):
        """Creates a scene if it is not already registered."""
        # Try and match an existing instance
        try:
            existing = cls[instance_id]

        # If we don't find one, make one
        except KeyError:
            existing = cls(instance_id=instance_id)

        return existing

    def on_registered(self):
        super().on_registered()

        SceneRegisteredSignal.invoke(target=self)

    def on_deregistered(self):
        SceneUnregisteredSignal.invoke(target=self)

        with self._context:
            Replicable.clear_graph()
            Signal.clear_graph()

        super().on_deregistered()
