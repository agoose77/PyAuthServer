from .enums import Roles, Netmodes
from .modifiers import is_simulated, is_event
from .rpc import RPC

from functools import wraps
from itertools import chain
from types import FunctionType
from traceback import print_exc
from inspect import getmembers
from collections import defaultdict


class TypeRegister(type):
    '''Registers all subclasses of parent class
    Stores class name: class mapping on parent._types'''

    def __new__(meta, name, parents, attrs):
        cls = super().__new__(meta, name, parents, attrs)

        if not hasattr(cls, "_types"):
            cls._types = []

            if hasattr(cls, "register_type"):
                cls.register_type()

        else:
            cls._types.append(cls)

            if hasattr(cls, "register_subtype"):
                cls.register_subtype()

        return cls

    @property
    def type_name(self):
        return self.__name__

    def from_type_name(self, type_name):
        for cls in self._types:
            if cls.__name__ == type_name:
                return cls

        raise LookupError("No class with name {}".format(type_name))


class EventListener:

    def listen_for_events(self, identifier=None):
        if identifier is None:
            identifier = self

        for name, val in getmembers(self):

            if not hasattr(val, "__annotations__"):
                continue

            if not (callable(val) and is_event(val)):
                continue

            Event.subscribe(identifier, val)

    def remove_from_events(self, identifier=None):
        if identifier is None:
            identifier = self

        for name, val in getmembers(self):

            if not hasattr(val, "__annotations__"):
                continue

            if not (callable(val) and is_event(val)):
                continue

            Event.unsubscribe(identifier, val)


class Event(metaclass=TypeRegister):

    @classmethod
    def register_subtype(cls):
        cls.subscribers = {}
        cls.isolated_subscribers = {}
        cls.children = {}

        cls.to_subscribe = {}
        cls.to_isolate = {}
        cls.to_child = defaultdict(list)

        cls.to_unsubscribe = []
        cls.to_unisolate = []
        cls.to_unchild = []

    @classmethod
    def register_type(cls):
        cls.register_subtype()

        cls.highest_event = cls

    @classmethod
    def unsubscribe(cls, identifier, callback):
        settings = callback.__annotations__
        event_cls = settings['event']
        event_cls.to_unsubscribe.append(identifier)
        event_cls.to_unisolate.append(identifier)

        if identifier in event_cls.children:
            for child in event_cls.children[identifier]:
                event_cls.remove_parent(child, identifier)

        for parent, children in event_cls.children.items():
            if identifier in children:
                event_cls.remove_parent(identifier, parent)

    @classmethod
    def set_parent(cls, identifier, parent_identifier):
        cls.to_child[parent_identifier].append(identifier)

    @classmethod
    def remove_parent(cls, identifier, parent_identifier):
        cls.to_unchild.append((identifier, parent_identifier))

    @classmethod
    def on_subscribed(cls, subscriber):
        pass

    @classmethod
    def get_total_subscribers(cls):
        return len(cls.subscribers) + len(cls.isolated_subscribers)

    @staticmethod
    def subscribe(identifier, callback):
        settings = callback.__annotations__
        event_cls = settings['event']

        data_dict = (event_cls.to_isolate if settings['context_dependant']
                     else event_cls.to_subscribe)
        data_dict[identifier] = callback, settings['accepts_event']

    @classmethod
    def update_graph(cls):
        for cl in cls._types:

            cl.subscribers.update(cl.to_subscribe)
            cl.isolated_subscribers.update(cl.to_isolate)
            cl.children.update(cl.to_child)

            local_to_subscribe = list(cl.to_subscribe.values())
            local_to_isolate = list(cl.to_isolate.values())

            cl.to_child.clear()
            cl.to_isolate.clear()
            cl.to_subscribe.clear()

            for identifier in local_to_subscribe:
                cl.on_subscribed(identifier)

            for key in cl.to_unsubscribe:
                cl.subscribers.pop(key, None)
            cl.to_unsubscribe.clear()

            for key in cl.to_unisolate:
                cl.isolated_subscribers.pop(key, None)
            cl.to_unisolate.clear()

            for (child, parent) in cl.to_unchild:
                cl.children[parent].remove(child)
                if not cl.children[parent]:
                    cl.children.pop(parent)
            cl.to_unchild.clear()

    @classmethod
    def update_targetted(cls, *args, target=None, **kwargs):
        targets = [target]

        while targets:
            try:
                target_ = targets.pop(0)
            except IndexError:
                return

            cls.update_graph()

            if target_ is not None:
                for target_child, (callback, supply_event) in\
                            cls.isolated_subscribers.items():
                    if target_child != target_:
                        continue

                    if supply_event:
                        kwargs['event'] = cls

                    callback(*args, **kwargs)
                    break

            if target_ in cls.children:
                targets.extend(cls.children[target_])

    @classmethod
    def invoke(cls, *args, target=None, **kwargs):
        cls.update_targetted(*args, target=target, **kwargs)

        for subscriber, (callback, supply_event) in cls.subscribers.items():

            if supply_event:
                kwargs['event'] = cls

            if target is not None:
                kwargs['target'] = target

            callback(*args, **kwargs)

        if cls.highest_event == cls:
            return

        try:
            parent = cls.__mro__[1]
        except IndexError:
            return

        parent.invoke(*args, target=target, **kwargs)

    @classmethod
    def listener(cls, global_listener=False, accepts_event=False):
        def wrapper(func):
            func.__annotations__['event'] = cls
            func.__annotations__['context_dependant'] = not global_listener
            func.__annotations__['accepts_event'] = accepts_event
            return func
        return wrapper


class InstanceRegisteredEvent(Event):
    pass


class InstanceUnregisteredEvent(Event):
    pass


class InstanceInstantiatedEvent(Event):
    pass


class CachedEvent(Event):
    cache = defaultdict(list)

    @classmethod
    def invoke(cls, *args, explicit=None, **kwargs):
        cls.update_targetted(*args, **kwargs)

        if explicit is None:
            cls.cache[cls].append((args, kwargs.copy()))

            target = kwargs.pop("target", None)

            for subscriber, (callback, supply_event) in cls.subscribers.items():

                if supply_event:
                    kwargs['event'] = cls

                if target is not None:
                    kwargs['target'] = target

                callback(*args, **kwargs)

        else:
            target = kwargs.pop("target", None)

            callback, supply_event = explicit

            if supply_event:
                kwargs['event'] = cls

            if target is not None:
                kwargs['target'] = target

            callback(*args, **kwargs)

        if cls.highest_event == cls:
            return

        try:
            parent = cls.__mro__[1]
        except IndexError:
            return

        kwargs['target'] = target
        parent.invoke(*args, **kwargs)

    @classmethod
    def on_subscribed(cls, subscriber_info):
        for previous_args, previous_kwargs in cls.cache[cls]:
            cls.invoke(*previous_args, explicit=subscriber_info, **previous_kwargs)


class InstanceNotifier:
    pass


class InstanceMixins(EventListener):

    def __init__(self, instance_id=None, register=False,
                 allow_random_key=False, **kwargs):
        self.allow_random_key = allow_random_key

        # Add to register queue
        self.request_registration(instance_id)

        # Run clean init function
        self.on_initialised()

        # Update graph
        if register:
            self.__class__.update_graph()

    def on_initialised(self):
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

        self.instance_id = instance_id
        self.__class__._to_register.add(self)

    @property
    def registered(self):
        return self._instances.get(self.instance_id) is self

    def __bool__(self):
        return self.registered

    def __str__(self):
        return "(RegisteredInstance {}: {})".format(self.__class__.__name__,
                                                    self.instance_id)
    __repr__ = __str__


class InstanceRegister(TypeRegister):

    def __new__(meta, name, parents, attrs):

        parents += (InstanceMixins,) 
        cls = super().__new__(meta, name, parents, attrs)

        if not hasattr(cls, "_instances"):
            cls._instances = {}
            cls._to_register = set()
            cls._to_unregister = set()

            if not hasattr(cls, '_registered_event'):
                cls._registered_event = InstanceRegisteredEvent
                cls._unregistered_event = InstanceUnregisteredEvent

        return cls

    def get_entire_graph_ids(cls, instigator=None):
        instance_ids = (k for k, v in cls._instances.items() if v != instigator)
        register_ids = (i.instance_id for i in cls._to_register if i != instigator)
        return chain(instance_ids, register_ids)

    def get_graph_instances(cls, only_real=True):
        if only_real:
            return cls._instances.values()
        return chain(cls._instances.values(), cls._to_register)

    def graph_has_instance(cls, instance_id):
        return instance_id in cls._instances

    def get_from_graph(cls, instance_id, only_real=True):
        try:
            return cls._instances[instance_id]
        except KeyError:
            # If we don't want the other values
            if only_real:
                raise LookupError

            try:
                return next(i for i in cls._to_register if i.instance_id==instance_id)
            except StopIteration:
                raise LookupError

    def remove_from_entire_graph(cls, instance_id):
        if not instance_id in cls._instances:
            return
        instance = cls._instances[instance_id]

        cls._unregister_from_graph(instance)

        for i in cls._to_register:
            if i.instance_id != instance_id:
                continue

            cls._to_register.remove(i)
            return i

    def get_random_id(cls):
        all_instances = list(cls.get_entire_graph_ids())

        for key in range(len(all_instances) + 1):
            if not key in all_instances:
                return key

    def update_graph(cls):
        if cls._to_register:
            for instance in cls._to_register.copy():
                cls._register_to_graph(instance)

        if cls._to_unregister:
            for instance in cls._to_unregister.copy():
                cls._unregister_from_graph(instance)

        if cls._to_register or cls._to_unregister:
            cls.update_graph()

    def _register_to_graph(cls, instance):
        if instance.registered:
            return
        cls._instances[instance.instance_id] = instance
        cls._to_register.remove(instance)

        instance.listen_for_events()
        Event.update_graph()

        try:
            cls._registered_event.invoke(target=instance)
        except Exception as err:
            raise err

    def _unregister_from_graph(cls, instance):
        cls._instances.pop(instance.instance_id)
        cls._to_unregister.remove(instance)

        try:
            cls._unregistered_event.invoke(target=instance)

        except Exception:
            raise

        finally:
            instance.remove_from_events()
            Event.update_graph()

    def __iter__(cls):
        return iter(cls._instances.values())
    
    def __len__(cls):
        return len(cls._instances)


class ReplicableRegister(InstanceRegister):

    def __new__(meta, cls_name, bases, attrs):
        # If this isn't the base class
        if bases:
            # Get all the member methods
            for name, value in attrs.items():
                # Check it's not in parents (will have been checked)
                if meta.found_in_parents(name, bases):
                    continue

                # Wrap them with permission
                if isinstance(value, (FunctionType, classmethod, staticmethod)):
                    # Recreate RPC from its function
                    if isinstance(value, RPC):
                        print("Found pre-wrapped RPC call: {}, re-wrapping... (any data defined in __init__ will be lost)".format(name))
                        value = value._func

                    value = meta.permission_wrapper(value)

                    # Automatically wrap RPC
                    if meta.is_rpc(value) and not isinstance(value, RPC):
                        value = RPC(value)

                    attrs[name] = value

        return super().__new__(meta, cls_name, bases, attrs)

    def is_rpc(func):
        try:
            annotations = func.__annotations__
        except AttributeError:
            if not hasattr(func, "__func__"):
                return False
            annotations = func.__func__.__annotations__

        try:
            return_type = annotations['return']
        except KeyError:
            return False

        return return_type in Netmodes

    def found_in_parents(name, parents):
        for parent in parents:
            if name in dir(parent):
                return True

    def permission_wrapper(func):
        simulated_proxy = Roles.simulated_proxy
        func_is_simulated = is_simulated(func)

        @wraps(func)
        def func_wrapper(*args, **kwargs):

            try:
                assumed_instance = args[0]

            # Static method needs no permission
            except IndexError:
                return func(*args, **kwargs)

            else:
                # Check that the assumed instance/class has context_subscribers role method
                if hasattr(assumed_instance, "roles"):
                    arg_roles = assumed_instance.roles
                    # Check that the roles are of an instance
                    try:
                        local_role = arg_roles.local
                    except AttributeError:
                        return

                    # Permission checks
                    if (local_role > simulated_proxy or(func_is_simulated and
                                            local_role >= simulated_proxy)):
                        return func(*args, **kwargs)

                    elif getattr(assumed_instance, "verbose_execution", False):
                        print("Error executing '{}': \
                               Function does not have permission:\n{}".format(
                                              func.__qualname__, arg_roles))

                elif getattr(assumed_instance, "verbose_execution", False):
                    print("Error executing {}: \
                        Function does not have permission roles")

        return func_wrapper

