from network.conditions import is_annotatable
from network.decorators import simulated

from bge import logic, types
from inspect import getmembers
from mathutils import Vector, Euler, Matrix, Quaternion

from game_system import IPhysicsObject

from .enums import CollisionType, PhysicsType
from .timer import Timer
from .signals import CollisionSignal, UpdateCollidersSignal


__all__ = ["BGEPhysicsObject", "BGEActorBase"]


def simulate_methods(cls):
    for name, member in getmembers(cls):
        if not is_annotatable(member):
            continue

        simulated(member)
    return cls


def create_object(name, position=None, rotation=None, scale=None):
    create_object = logic.getCurrentScene().addObject
    position_matrix = Matrix.Translation(position or Vector())
    scale_matrix = Matrix.Scale(scale or 1.0, 4)
    rotation_matrix = (rotation or Euler())\
                .to_quaternion().to_matrix().to_4x4()
    transform = position_matrix * scale_matrix * rotation_matrix

    try:
        return create_object(name, transform, 0, -1)

    except ValueError:
        raise ValueError("Could not find object with name {}".format(name))


class BGEPhysicsObject(IPhysicsObject):

    @property
    def angular(self):
        if not self.has_dynamics:
            return Vector()

        return self.object.localAngularVelocity

    @angular.setter
    def angular(self, vel):
        if not self.has_dynamics:
            return

        self.object.localAngularVelocity = vel

    @property
    def collision_group(self):
        '''Physics collision group

        :returns: physics bitmask of collision group
        :requires: must be within -1 and 256'''
        return self.object.collisionGroup

    @collision_group.setter
    def collision_group(self, group):
        if self.object.collisionGroup == group:
            return

        assert -1 < group < 256
        self.object.collisionGroup = group

    @property
    def collision_mask(self):
        '''Physics collision mask

        :returns: physics bitmask of collision mask
        :requires: must be within -1 and 256'''
        return self.object.collisionMask

    @collision_mask.setter
    def collision_mask(self, mask):
        if self.object.collisionMask == mask:
            return

        assert -1 < mask < 256
        self.object.collisionMask = mask

    @property
    def colour(self):
        '''The object's colour'''
        return self.object.color

    @colour.setter
    def colour(self, value):
        self.object.color = value

    @property
    def has_dynamics(self):
        return self.physics in (PhysicsType.rigid_body, PhysicsType.dynamic)

    @property
    def lifespan(self):
        '''The time before the object is destroyed'''
        try:
            return self._timer.remaining

        except AttributeError:
            return 0.0

    @lifespan.setter
    def lifespan(self, value):
        if hasattr(self, "_timer"):
            self._timer.delete()
            del self._timer

        if value > 0:
            self._timer = Timer(value)
            self._timer.on_target = self.delete

    @property
    def local_position(self):
        return self.object.localPosition

    @local_position.setter
    def local_position(self, pos):
        self.object.localPosition = pos

    @property
    def local_rotation(self):
        return self.object.localOrientation.to_euler()

    @local_rotation.setter
    def local_rotation(self, ori):
        self.object.localOrientation = ori

    @property
    def mass(self):
        ''':returns: the mass of this object'''
        return self.object.mass

    @property
    def parent(self):
        '''Relational parent of object

        :returns: parent of object
        :requires: instance must subclass :py:class:`PhysicsObject`'''
        return self._parent

    @property
    def physics(self):
        '''The physics type of this object

        :returns: physics type of object, see :py:class:`bge_network.enums.PhysicsType`'''
        physics_type = self.object.physicsType
        if not getattr(self.object, "meshes", []):
            return logic.KX_PHYSICS_NO_COLLISION
        return physics_type
        # FIXED BY NEW PATCH (NOT SURE ACUTALLY)

    @property
    def position(self):
        return self.object.worldPosition

    @position.setter
    def position(self, pos):
        self.object.worldPosition = pos

    @property
    def rotation(self):
        return self.object.worldOrientation.to_euler()

    @rotation.setter
    def rotation(self, rot):
        self.object.worldOrientation = rot

    @property
    def sockets(self):
        return {s['socket']: s for s in self.object.childrenRecursive
                if "socket" in s}

    @property
    def suspended(self):
        '''The Physics state of the object'''
        if self.physics in (PhysicsType.navigation_mesh,
                            PhysicsType.no_collision):
            return True

        try:
            return not self.object.useDynamics

        except AttributeError:
            try:
                return self._suspended
            except AttributeError:
                self._suspended = False
                return self._suspended

    @suspended.setter
    def suspended(self, value):
        if self.physics in (PhysicsType.navigation_mesh,
                            PhysicsType.no_collision):
            return

        if self.object.parent:
            return

        # Legacy code
        try:
            dynamics = self.object.useDynamics
            self.object.useDynamics = not value

        except AttributeError:
            suspended = self.suspended
            if value and not suspended:
                self.object.suspendDynamics()
            elif not value and suspended:
                self.object.restoreDynamics()
            self._suspended = value

    @property
    def transform(self):
        return self.object.worldTransform

    @transform.setter
    def transform(self, val):
        self.object.worldTransform = val

    @property
    def velocity(self):
        if not self.has_dynamics:
            return Vector()

        return self.object.localLinearVelocity

    @velocity.setter
    def velocity(self, vel):
        if not self.has_dynamics:
            return

        self.object.localLinearVelocity = vel

    @property
    def visible(self):
        ''':returns: the visible state of this object'''
        open_stack = [self.object]

        while open_stack:
            game_obj = open_stack.pop()
            if (game_obj.meshes and game_obj.visible):
                return True

            open_stack.extend(game_obj.childrenRecursive)
        return False

    def add_child(self, instance):
        '''Adds a child to this object

        :param instance: instance to add
        :requires: instance must subclass :py:class:`PhysicsObject`'''
        self.children.add(instance)
        self.child_entities.add(instance.object)

    def pop_child(self):
        '''Removes a child from this object

        :param instance: instance to remove
        :requires: instance must subclass :py:class:`PhysicsObject`'''
        instance = self.children.pop()
        self.child_entities.remove(instance.object)
        instance.set_parent(None)

    def remove_child(self, instance):
        '''Removes a child from this object

        :param instance: instance to remove
        :requires: instance must subclass :py:class:`PhysicsObject`'''
        self.children.remove(instance)
        self.child_entities.remove(instance.object)
        instance.set_parent(None)

    def set_parent(self, parent, socket_name=None):
        if parent is None and self._parent is not None:
            # Remove parent's child (might be socket)
            if self in self.parent.children:
                self._parent.remove_child(self)
            self.object.removeParent()
            self._parent = None

        elif isinstance(parent, BGEPhysicsObject):
            # Remove existing parent
            if self._parent:
                self.set_parent(None)

            parent.add_child(self)
            physics_obj = (parent.object if socket_name is None
                           else parent.sockets[socket_name])

            self.object.setParent(physics_obj)
            self._parent = parent

        else:
            raise TypeError("Could not set parent\
                with type {}".format(type(parent)))

    def delete(self):
        # Unregister from parent
        if self.parent:
            self.parent.remove_child(self)

        if hasattr(self, "_timer"):
            self._timer.delete()

        while self.children:
            self.pop_child()
        self.object.endObject()

    def register(self, game_obj):
        self.object = game_obj

        self._parent = None
        self.children = set()
        self.child_entities = set()


@simulate_methods
class BGEActorBase(BGEPhysicsObject):

    def on_initialised(self):
        game_object = create_object(self.__class__.entity_name)

        self.register(game_object)

        self._new_colliders = set()
        self._old_colliders = set()
        self._registered = set()
        self._register_callback()

    @property
    def colliding(self):
        '''The collision status of the object'''
        return bool(self._registered)

    def colliding_with(self, other):
        '''Determines if the object is colliding with another object

        :param other: object to evaluate
        :returns: result of condition'''
        return other in self._registered

    @staticmethod
    def from_object(game_obj):
        return game_obj.get('binding')

    def delete(self):
        pass

    def register(self, game_object):
        game_object['binding'] = self

        super().register(game_object)

    def on_unregistered(self):
        super().on_unregistered()

        super().delete()

    def _on_collision(self, other, data):
        if not self or self.suspended:
            return

        # If we haven't already stored the collision
        self._new_colliders.add(other)

        if not other in self._registered:
            self._registered.add(other)
            CollisionSignal.invoke(other, CollisionType.started,
                                   data, target=self)

    def _register_callback(self):
        if self.physics in (PhysicsType.navigation_mesh,
                            PhysicsType.no_collision):
            return

        callbacks = self.object.collisionCallbacks
        callbacks.append(self._on_collision)

    @UpdateCollidersSignal.global_listener
    def _update_colliders(self):
        if self.suspended:
            return

        assert self

        # If we have a stored collision
        difference = self._old_colliders.difference(self._new_colliders)
        self._old_colliders, self._new_colliders = self._new_colliders, set()

        if not difference:
            return

        callback = CollisionSignal.invoke
        for obj in difference:
            self._registered.remove(obj)
            if not obj.invalid:
                callback(obj, CollisionType.ended, None, target=self)
