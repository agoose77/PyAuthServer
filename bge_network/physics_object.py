from bge import logic
from functools import lru_cache
from mathutils import Vector
from network.decorators import simulated
from network.signals import SignalListener
from . import enums, signals, bge_data, timer


class PhysicsObject:
    entity_name = ""
    entity_class = bge_data.GameObject

    def on_initialised(self):
        self.object = self.entity_class(self.entity_name)

        self.parent = None
        self.children = set()
        self.child_entities = set()

        self._suspended_parent = None
        self._new_colliders = set()
        self._old_colliders = set()
        self._registered = set()

        self._register_callback()
        self._establish_relationship()

    @staticmethod
    def from_object(obj):
        return obj.get("owner")

    @simulated
    def _establish_relationship(self):
        self.object['owner'] = self

    @property
    def lifespan(self):
        if hasattr(self, "_timer"):
            return self._timer.target
        return 0

    @lifespan.setter
    def lifespan(self, value):
        if hasattr(self, "_timer"):
            self._timer.delete()
            del self._timer
        if value > 0:
            self._timer = timer.Timer(value,
                            on_target=self.request_unregistration)

    @property
    def suspended(self):
        if self.physics in (enums.PhysicsType.navigation_mesh,
                            enums.PhysicsType.no_collision):
            return True
        return not self.object.useDynamics

    @suspended.setter
    def suspended(self, value):
        if self.physics in (enums.PhysicsType.navigation_mesh,
                            enums.PhysicsType.no_collision):
            return

        if self.object.parent:
            return
        self.object.useDynamics = not value

    @property
    def colliding(self):
        return bool(self._registered)

    @simulated
    def colliding_with(self, other):
        return other in self._registered

    @simulated
    def _register_callback(self):
        if self.physics in (enums.PhysicsType.navigation_mesh,
                            enums.PhysicsType.no_collision):
            return

        callbacks = self.object.collisionCallbacks
        callbacks.append(self._on_collide)

    @simulated
    def _on_collide(self, other, data):
        if not self or self.suspended:
            return

        # If we haven't already stored the collision
        self._new_colliders.add(other)

        if not other in self._registered:
            self._registered.add(other)
            signals.CollisionSignal.invoke(other, True, data, target=self)

    @signals.UpdateCollidersSignal.global_listener
    @simulated
    def _update_colliders(self):
        if not self or self.suspended:
            return

        # If we have a stored collision
        difference = self._old_colliders.difference(self._new_colliders)
        self._old_colliders, self._new_colliders = self._new_colliders, set()

        if not difference:
            return

        callback = signals.CollisionSignal.invoke
        for obj in difference:
            self._registered.remove(obj)
            if not obj.invalid:
                callback(obj, False, None, target=self)

    def on_unregistered(self):
        # Unregister from parent
        if self.parent:
            self.parent.remove_child(self)

        if hasattr(self, "_timer"):
            self._timer.delete()

        self.children.clear()
        self.child_entities.clear()
        self.object.endObject()

    @simulated
    def add_child(self, actor):
        self.children.add(actor)
        self.child_entities.add(actor.object)

    @simulated
    def remove_child(self, actor):
        self.children.remove(actor)
        self.child_entities.remove(actor.object)

    @simulated
    def set_parent(self, actor, socket_name=None):
        if socket_name is None:
            parent_obj = actor.object

        elif socket_name in actor.sockets:
            parent_obj = actor.sockets[socket_name]

        else:
            raise LookupError("Parent: {} does not have socket named {}".
                            format(actor, socket_name))

        self.object.setParent(parent_obj)
        self.parent = actor
        actor.add_child(self)

    @simulated
    def remove_parent(self):
        self.parent.remove_child(self)
        self.object.setParent(None)

    @property
    def collision_group(self):
        return self.object.collisionGroup

    @collision_group.setter
    def collision_group(self, group):
        if self.object.collisionGroup == group:
            return
        self.object.collisionGroup = group

    @property
    def collision_mask(self):
        return self.object.collisionMask

    @collision_mask.setter
    def collision_mask(self, mask):
        if self.object.collisionMask == mask:
            return
        self.object.collisionMask = mask

    @property
    def visible(self):
        obj = self.object
        return (obj.visible and obj.meshes) or any(o.visible and o.meshes
                for o in obj.childrenRecursive)

    @property
    def mass(self):
        return self.object.mass

    @property
    @lru_cache()
    def physics(self):
        physics_type = self.object.physicsType
        if not getattr(self.object, "meshes", []):
            return logic.KX_PHYSICS_NO_COLLISION
        return physics_type

    @property
    def sockets(self):
        return {s['socket']: s for s in
                self.object.childrenRecursive if "socket" in s}

    @property
    def has_dynamics(self):
        return self.physics in (enums.PhysicsType.rigid_body, enums.PhysicsType.dynamic)

    @property
    def transform(self):
        return self.object.worldTransform

    @transform.setter
    def transform(self, val):
        self.object.worldTransform = val

    @property
    def rotation(self):
        return self.object.worldOrientation.to_euler()

    @rotation.setter
    def rotation(self, rot):
        self.object.worldOrientation = rot

    @property
    def position(self):
        return self.object.worldPosition

    @position.setter
    def position(self, pos):
        self.object.worldPosition = pos

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
    def angular(self):
        if not self.has_dynamics:
            return Vector()

        return self.object.localAngularVelocity

    @angular.setter
    def angular(self, vel):
        if not self.has_dynamics:
            return

        self.object.localAngularVelocity = vel

