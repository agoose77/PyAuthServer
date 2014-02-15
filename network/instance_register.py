from .signals import SignalListener
from .type_register import TypeRegister


from random import choice
from itertools import chain

__all__ = ['InstanceRegister', 'InstanceMixins']


class InstanceMixins(SignalListener):

    def __init__(self, instance_id=None, register=False,
                 allow_random_key=False, **kwargs):
        super().__init__()

        self.allow_random_key = allow_random_key

        # Add to register queue
        self.request_registration(instance_id)

        # Run clean init function
        self.on_initialised()

        # Update graph
        if register:
            self.__class__.update_graph()

    def validate_id(self, instance_id):
        return True

    def on_initialised(self):
        pass

    def on_registered(self):
        pass

    def on_unregistered(self):
        pass

    def request_unregistration(self, unregister=False):
        if not self.registered:
            return

        self.__class__._to_unregister.add(self)

        if unregister:
            self.__class__._unregister_from_graph()

    def request_registration(self, instance_id):
        if instance_id is None:
            assert self.allow_random_key, "No key specified"
            instance_id = self.__class__.get_random_id()

        if not self.validate_id(instance_id):
            raise IndexError("Instance ID requested is not available")

        self.instance_id = instance_id
        self.__class__._to_register.add(self)

    @property
    def registered(self):
        return self._instances.get(self.instance_id) is self

    def __bool__(self):
        return self.registered

    def __repr__(self):
        if not self.registered:
            return "(Instance {})".format(self.__class__.__name__)
        return "(Instance {}: id={})".format(self.__class__.__name__,
                                                    self.instance_id)


class InstanceRegister(TypeRegister):

    def __new__(self, name, parents, attrs):

        parents += (InstanceMixins,)
        cls = super().__new__(self, name, parents, attrs)

        if not hasattr(cls, "_instances"):
            cls._instances = {}
            cls._to_register = set()
            cls._to_unregister = set()

        return cls

    def get_entire_graph_ids(cls, instigator=None):  # @NoSelf
        instance_ids = (k for k, v in cls._instances.items()
                        if v != instigator)
        register_ids = (i.instance_id for i in cls._to_register
                        if i != instigator)
        return chain(instance_ids, register_ids)

    def get_graph_instances(cls, only_real=True):  # @NoSelf
        if only_real:
            return cls._instances.values()
        return chain(cls._instances.values(), cls._to_register)

    def graph_has_instance(cls, instance_id):  # @NoSelf
        return instance_id in cls._instances

    def get_from_graph(cls, instance_id, only_real=True):  # @NoSelf
        try:
            return cls._instances[instance_id]
        except KeyError:
            # If we don't want the other values
            if only_real:
                raise LookupError

            try:
                return next(i for i in cls._to_register
                            if i.instance_id == instance_id)
            except StopIteration:
                raise LookupError

    def remove_from_entire_graph(cls, instance_id):  # @NoSelf
        if not instance_id in cls._instances:
            return
        instance = cls._instances[instance_id]

        if not instance in cls._to_unregister:
            cls._to_unregister.add(instance)

        cls._unregister_from_graph(instance)

        for i in cls._to_register:
            if i.instance_id != instance_id:
                continue

            cls._to_register.remove(i)
            return i

    def get_random_id(cls):  # @NoSelf
        all_instances = list(cls.get_entire_graph_ids())

        for key in range(len(all_instances) + 1):
            if not key in all_instances:
                return key

    def update_graph(cls):  # @NoSelf
        if cls._to_register:
            for instance in cls._to_register.copy():
                cls._register_to_graph(instance)

        if cls._to_unregister:
            for instance in cls._to_unregister.copy():
                cls._unregister_from_graph(instance)

        if cls._to_register or cls._to_unregister:
            cls.update_graph()

    def _register_to_graph(cls, instance):  # @NoSelf
        if instance.registered:
            return

        cls._instances[instance.instance_id] = instance
        cls._to_register.remove(instance)

        try:
            instance.on_registered()
        except Exception as err:
            raise err

    def _unregister_from_graph(cls, instance):  # @NoSelf
        cls._instances.pop(instance.instance_id)
        cls._to_unregister.remove(instance)

        try:
            instance.on_unregistered()

        except Exception:
            raise

        finally:
            instance.unregister_signals()

    def __iter__(cls, iter=iter):  # @NoSelf
        return iter(cls._instances.values())

    def __len__(cls, len=len):  # @NoSelf
        return len(cls._instances)
