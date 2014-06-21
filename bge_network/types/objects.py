from collections import namedtuple
from contextlib import contextmanager
from math import radians

from network.decorators import simulated, simulate_methods
from network.iterators import take_single
from game_system.object_mixins import (IAnimatedObjectMixin, IPhysicsObjectMixin, ITransformObjectMixin,
                                       ICameraObjectMixin, INavmeshObjectMixin, ILampObjectMixin)
from game_system.enums import Axis, CollisionType, PhysicsType, AnimationBlend, AnimationMode
from game_system.timer import Timer
from game_system.signals import CollisionSignal, UpdateCollidersSignal

from bge import logic, types
from mathutils import Vector, Euler, Matrix


__all__ = ["BGEBaseObject", "BGEActorBase", "BGECameraObject", "BGECameraBase", "RayTestResult", "BGEPawnBase",
           "BGELampBase", "BGENavmeshBase"]


RayTestResult = namedtuple("RayTestResult", "hit_position hit_normal hit_object distance")
CollisionResult = namedtuple("CollisionResult", "hit_object collision_type hit_contacts")
CollisionContact = namedtuple("CollisionContact", "hit_position hit_normal hit_impulse hit_force")


def create_object(name, position=None, rotation=None, scale=None):
    """Spawn an object into the current scene

    :param name: name of BGE resource to spawn
    :param position: position of spawned object
    :param rotation: rotation of spawned object
    :param scale: scale of spawned object
    :returns: created object
    """
    object_factory = logic.getCurrentScene().addObject
    position_matrix = Matrix.Translation(position or Vector())
    scale_matrix = Matrix.Scale(scale or 1.0, 4)
    rotation_matrix = (rotation or Euler()).to_quaternion().to_matrix().to_4x4()
    transform = position_matrix * scale_matrix * rotation_matrix

    try:
        return object_factory(name, transform, 0, -1)

    except ValueError:
        raise ValueError("Could not find object with name {}".format(name))


class BGEBaseObject(IPhysicsObjectMixin, ITransformObjectMixin):
    """Base class for Physics objects"""

    @property
    def collision_group(self):
        """Physics collision group

        :returns: physics bitmask of collision group
        :requires: must be within -1 and 256
        """
        return self.object.collisionGroup

    @collision_group.setter
    def collision_group(self, group):
        if self.object.collisionGroup == group:
            return

        assert -1 < group < 256
        self.object.collisionGroup = group

    @property
    def collision_mask(self):
        """Physics collision mask

        :returns: physics bitmask of collision mask
        :requires: must be within -1 and 256"""
        return self.object.collisionMask

    @collision_mask.setter
    def collision_mask(self, mask):
        if self.object.collisionMask == mask:
            return

        assert -1 < mask < 256
        self.object.collisionMask = mask

    @property
    def colour(self):
        """Colour of object

        :rtype: list
        """
        return self.object.color

    @colour.setter
    def colour(self, value):
        self.object.color = value

    @property
    def has_dynamics(self):
        """Physics dynamics status of object

        :rtype: bool
        """
        return self.physics in (PhysicsType.rigid_body, PhysicsType.dynamic)

    @property
    def lifespan(self):
        """Time before object is destroyed

        :rtype: float
        """
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
    def local_angular(self):
        return self.object.localAngularVelocity

    @local_angular.setter
    def local_angular(self, angular):
        self.object.localAngularVelocity = angular

    @property
    def local_position(self):
        """Local position of object

        :rtype: :py:class:`mathutils.Vector`
        """
        return self.object.localPosition

    @local_position.setter
    def local_position(self, pos):
        self.object.localPosition = pos

    @property
    def local_rotation(self):
        """Local rotation of object

        :rtype: :py:class:`mathutils.Euler`
        """
        return self.object.localOrientation.to_euler()

    @local_rotation.setter
    def local_rotation(self, ori):
        self.object.localOrientation = ori

    @property
    def local_velocity(self):
        return self.object.localLinearVelocity

    @local_velocity.setter
    def local_velocity(self, velocity):
        self.object.localLinearVelocity = velocity

    @property
    def mass(self):
        """Mass of object

        :rtype: float
        """
        return self.object.mass

    @property
    def parent(self):
        """Relational parent of object

        :returns: parent of object
        :requires: instance must subclass :py:class:`PhysicsObject`"""
        return self._parent

    @property
    def physics(self):
        """The physics type of this object

        :returns: physics type of object, see :py:class:`bge_network.enums.PhysicsType`
        """
        physics_type = self.object.physicsType

        # Might not be needed but enforce checks anyway
        if not getattr(self.object, "meshes", []):
            return PhysicsType.no_collision

        # Should work correctly with new patch
        physics_map = {logic.KX_PHYSICS_STATIC: PhysicsType.static, logic.KX_PHYSICS_DYNAMIC: PhysicsType.dynamic,
                       logic.KX_PHYSICS_RIGID_BODY: PhysicsType.rigid_body,
                       logic.KX_PHYSICS_SOFT_BODY: PhysicsType.soft_body,
                       logic.KX_PHYSICS_OCCLUDER: PhysicsType.occluder, logic.KX_PHYSICS_SENSOR: PhysicsType.sensor,
                       logic.KX_PHYSICS_NAVIGATION_MESH: PhysicsType.navigation_mesh,
                       logic.KX_PHYSICS_CHARACTER: PhysicsType.character,
                       logic.KX_PHYSICS_NO_COLLISION: PhysicsType.no_collision}

        return physics_map[physics_type]

    @property
    def sockets(self):
        """Socket dictionary of object

        :rtype: dict
        """
        return {s['socket']: s for s in self.object.childrenRecursive if "socket" in s}

    @property
    def suspended(self):
        """Physics state of the object

        :rtype: bool
        """
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
        """World transformation of object

        :rtype: :py:class:`mathutils.Vector`
        """

        return self.object.worldTransform

    @transform.setter
    def transform(self, val):
        self.object.worldTransform = val

    @property
    def world_angular(self):
        """World world_angular velocity of object

        :rtype: :py:class:`mathutils.Vector`
        """
        if not self.has_dynamics:
            return Vector()

        return self.object.worldAngularVelocity

    @world_angular.setter
    def world_angular(self, vel):
        if not self.has_dynamics:
            return

        self.object.worldAngularVelocity = vel

    @property
    def world_position(self):
        """World position of object

        :rtype: :py:class:`mathutils.Vector`
        """
        return self.object.worldPosition

    @world_position.setter
    def world_position(self, pos):
        self.object.worldPosition = pos

    @property
    def world_rotation(self):
        """World rotation of object

        :rtype: :py:class:`mathutils.Vector`
        """
        return self.object.worldOrientation.to_euler()

    @world_rotation.setter
    def world_rotation(self, rotation):
        self.object.worldOrientation = rotation

    @property
    def world_velocity(self):
        """World velocity of object

        :rtype: :py:class:`mathutils.Vector`
        """
        if not self.has_dynamics:
            return Vector()

        return self.object.worldLinearVelocity

    @world_velocity.setter
    def world_velocity(self, vel):
        if not self.has_dynamics:
            return

        self.object.worldLinearVelocity = vel

    @property
    def visible(self):
        """Visibility of object]

        :rtype: bool
        """
        open_stack = [self.object]

        while open_stack:
            game_obj = open_stack.pop()
            if game_obj.meshes and game_obj.visible:
                return True

            open_stack.extend(game_obj.childrenRecursive)

        return False

    def add_child(self, instance):
        """Add a child to this object

        :param instance: instance to add
        :requires: instance must subclass :py:class:`PhysicsObject`
        """
        self.children.add(instance)
        self.child_entities.add(instance.object)

    @simulated
    def align_to(self, vector, factor=1, axis=Axis.y):
        if not vector.length:
            return

        if axis == Axis.x:
            forward_axis = "X"
        elif axis == Axis.y:
            forward_axis = "Y"
        elif axis == Axis.z:
            forward_axis = "Z"

        rotation_quaternion = vector.to_track_quat(forward_axis, "Z")
        current_rotation = self.world_rotation.to_quaternion()
        self.world_rotation = (current_rotation.slerp(rotation_quaternion, factor)).to_euler()

    def delete(self):
        # Unregister from parent
        if self.parent:
            self.parent.remove_child(self)

        if hasattr(self, "_timer"):
            self._timer.delete()

        while self.children:
            self.pop_child()
        self.object.endObject()

    @staticmethod
    def from_object(obj):
        """Find the wrapper class for a BGE object"""
        return obj.get('binding')

    @classmethod
    def factory(cls, name):
        """Create a new instance of this class from a name

        :param name: name of object to create
        """
        new_wrapper = cls()
        new_wrapper.register(name)

        return new_wrapper

    @classmethod
    def factory_from(cls, game_object):
        """Create a new instance of this class from an existing BGE object

        :param game_object: BGE object
        """
        new_wrapper = cls()
        new_wrapper.register_from(game_object)

        return new_wrapper

    def get_direction(self, axis):
        """Get the axis vector of this object in world space

        :param axis: :py:code:`bge_network.enums.Axis` value
        :rtype: :py:code:`mathutils.Vector`
        """
        vector = [0, 0, 0]
        if axis == Axis.x:
            vector[0] = 1
        elif axis == Axis.y:
            vector[1] = 1
        elif axis == Axis.z:
            vector[2] = 1
        return Vector(self.object.getAxisVect(vector))

    def pop_child(self):
        """Remove a child from this object

        :param instance: instance to remove
        :requires: instance must subclass :py:class:`PhysicsObject`
        """
        instance = self.children.pop()
        self.child_entities.remove(instance.object)
        instance.set_parent(None)

    def register(self, name):
        """Register new BGE object to this wrapper

        :param name: name of BGE object
        """
        game_obj = create_object(name)
        self.register_from(game_obj)

    def register_from(self, game_obj):
        """Register BGE object to this wrapper

        :param game_obj: BGE object
        """
        self._parent = None
        self.children = set()
        self.child_entities = set()

        self.object = game_obj
        self.object['binding'] = self

    def remove_child(self, instance):
        """Remove a child from this object

        :param instance: instance to remove
        :requires: instance must subclass :py:class:`PhysicsObject`
        """
        self.children.remove(instance)
        self.child_entities.remove(instance.object)
        instance.set_parent(None)

    def set_parent(self, parent, socket_name=None):
        """Set the parent of this object

        :param parent: instance of :py:class:`PhysicsObject`
        :param socket_name: optional name of socket to parent to
        """
        if parent is None and self._parent is not None:
            # Remove parent's child (might be socket)
            if self in self.parent.children:
                self._parent.remove_child(self)
            self.object.removeParent()
            self._parent = None

        elif isinstance(parent, BGEBaseObject):
            # Remove existing parent
            if self._parent:
                self.set_parent(None)

            parent.add_child(self)
            physics_obj = (parent.object if socket_name is None
                           else parent.sockets[socket_name])

            self.object.setParent(physics_obj)
            self._parent = parent

        else:
            raise TypeError("Could not set parent with type {}".format(type(parent)))

    def trace_ray(self, target, source=None, distance=0.0, local_space=False):
        """Perform a ray trace to a target

        :param target: target to trace towards
        :param source: optional origin of trace, otherwise object position
        :param distance: distance to use instead of vector length
        :rtype: :py:class:`bge_network.object_types.RayTestResult`
        """
        if source is None:
            source = self.world_position

        result = self.object.rayCast(target, source, distance)

        if not any(result):
            return None

        hit_bge_object, hit_position, hit_normal = result
        hit_object = BGEBaseObject.from_object(hit_bge_object)
        hit_distance = (hit_position - source).length

        return RayTestResult(hit_position, hit_normal, hit_object, hit_distance)


class BGECameraObject(BGEBaseObject, ICameraObjectMixin):
    """Base class for Camera objects"""

    @property
    def active(self):
        return self.object == logic.getCurrentScene().active_camera

    @active.setter
    def active(self, status):
        if status:
            logic.getCurrentScene().active_camera = self.object

    @property
    def lens(self):
        return self.object.lens

    @lens.setter
    def lens(self, value):
        self.object.lens = value

    @property
    def fov(self):
        return self.object.fov

    @fov.setter
    def fov(self, value):
        self.object.fov = value

    @property
    def world_rotation(self):
        rotation = Euler((-radians(90), 0, 0))
        rotation.rotate(self.object.worldOrientation)
        return rotation

    @world_rotation.setter
    def world_rotation(self, rot):
        rotation = Euler((radians(90), 0, 0))
        rotation.rotate(rot)
        self.object.worldOrientation = rotation

    @property
    def local_rotation(self):
        rotation = Euler((-radians(90), 0, 0))
        rotation.rotate(self.object.localOrientation)
        return rotation

    @local_rotation.setter
    def local_rotation(self, rot):
        rotation = Euler((radians(90), 0, 0))
        rotation.rotate(rot)
        self.object.localOrientation = rotation

    def is_point_in_frustum(self, point):
        """Determine if a point resides in the camera frustum

        :param point: :py:code:`mathutils.Vector`
        :rtype: bool
        """
        return self.object.pointInsideFrustum(point)

    def is_sphere_in_frustum(self, point, radius):
        """Determine if a sphere resides in the camera frustum

        :param point: :py:code:`mathutils.Vector`
        :param radius: radius of sphere
        :rtype: bool
        """
        return self.object.sphereInsideFrustum(point, radius) != self.object.OUTSIDE

    def screen_trace_ray(self, distance, x=0.5, y=0.5):
        """Perform a ray trace along screen vector

        :param distance: distance to travel
        :param x: screen space x coordinate
        :param y: screen space y coordinate
        """
        vector = self.object.getScreenRay(x, y)
        return self.trace_ray(vector, distance)

    def get_direction(self, axis):
        """Get the axis vector of this object in world space

        :param axis: :py:code:`bge_network.enums.Axis` value
        :rtype: :py:code:`mathutils.Vector`
        """
        vector = [0, 0, 0]
        if axis == Axis.x:
            vector[0] = 1
        elif axis == Axis.y:
            vector[2] = -1
        elif axis == Axis.z:
            vector[1] = 1
        return Vector(self.object.getAxisVect(vector))


class BGEAnimatedObject(BGEBaseObject, IAnimatedObjectMixin):

    def get_animation_frame(self, layer=0):
        """Get the current frame of the animation

        :param layer: layer of animation
        """
        return int(self.animation_object.getActionFrame(layer))

    def play_animation(self, name, start, end, layer=0, priority=0, blend=0.0, mode=AnimationMode.play, weight=0.0,
                       speed=1.0, blend_mode=AnimationBlend.interpolate):
        """Play animation resource

        :param name: name of animation
        :param start: start frame of animation
        :param end: end frame of animation
        :param layer: layer to play animation on
        :param priority: priority of animation (lower is higher)
        :param blend: blending value
        :param mode: see :py:class:`bge_network.enums.AnimationMode`
        :param weight: animation weighting
        :param speed: speed to play animation
        :param blend_mode: see :py:class:`bge_network.enums.AnimationBlend`
        """

        # Define conversions from Blender behaviours to Network animation enum
        bge_play_constants = {AnimationMode.play: logic.KX_ACTION_MODE_PLAY,
                              AnimationMode.loop: logic.KX_ACTION_MODE_LOOP,
                              AnimationMode.ping_pong: logic.KX_ACTION_MODE_PING_PONG}

        bge_blend_constants = {AnimationBlend.interpolate: logic.KX_ACTION_BLEND_BLEND,
                               AnimationBlend.add: logic.KX_ACTION_BLEND_ADD}

        ge_play_mode = bge_play_constants[mode]
        ge_blend_mode = bge_blend_constants[blend_mode]

        # Play animation
        self.animation_object.playAction(name, start, end, layer, priority, blend, ge_play_mode, weight, speed=speed,
                                         blend_mode=ge_blend_mode)

    def is_playing_animation(self, layer):
        """Determine if the object is playing an animation for this layer

        :param layer: animation layer to check
        """
        return self.animation_object.isPlayingAction(layer)

    def register_from(self, game_obj):
        super().register_from(game_obj)

        self.animation_object = game_obj

    def stop_animation(self, layer=0):
        """Stop playing animation on certain layer

        :param layer: layer to stop animation playing on
        """
        self.animation_object.stopAction(layer)



@simulate_methods
class BGEActorBase(BGEBaseObject):
    """Base class for Actor"""

    entity_name = ""

    def on_initialised(self):
        self.register(self.__class__.entity_name)

        self._new_colliders = set()
        self._old_colliders = set()
        self._registered = set()
        self._register_callback()

    @property
    def is_colliding(self):
        """The collision status of the object"""
        return bool(self._registered)

    def colliding_with(self, other):
        """Determines if the object is colliding with another object

        :param other: object to evaluate
        :returns: result of condition"""
        return other in self._registered

    def delete(self):
        pass

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

            hit_object = BGEBaseObject.from_object(other)
            hit_contacts = [CollisionContact(c.hitPosition, c.hitNormal, c.hitImpulse, c.hitForce) for c in data]
            result = CollisionResult(hit_object, CollisionType.started, hit_contacts)

            CollisionSignal.invoke(result, target=self)

    def _register_callback(self):
        if self.physics in (PhysicsType.navigation_mesh, PhysicsType.no_collision):
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
        ended_collision = CollisionType.ended

        for obj in difference:
            self._registered.remove(obj)
            if not obj.invalid:
                hit_object = BGEBaseObject.from_object(obj)
                result = CollisionResult(hit_object, ended_collision, None)
                callback(result, target=self)


@simulate_methods
class BGECameraBase(BGECameraObject, BGEActorBase):
    """Base class for Camera"""

    @contextmanager
    def active_context(self):
        cam = self.object
        scene = cam.scene

        old_camera = scene.active_camera
        scene.active_camera = cam
        yield
        if old_camera:
            scene.active_camera = old_camera

    def delete(self):
        pass

    def on_unregistered(self):
        super().on_unregistered()

        super().delete()


@simulate_methods
class BGEPawnBase(BGEAnimatedObject, BGEActorBase):
    """Base class for Pawn"""

    def on_initialised(self):
        super().on_initialised()

        skeleton = take_single(c for c in self.object.childrenRecursive if isinstance(c, types.BL_ArmatureObject))
        self.animation_object = BGEBaseObject.factory_from(skeleton)


@simulate_methods
class BGELampBase(BGEAnimatedObject, BGEActorBase, ILampObjectMixin):

    @property
    def intensity(self):
        return self.object.energy

    @intensity.setter
    def intensity(self, energy):
        self.object.energy = energy


@simulate_methods
class BGENavmeshBase(BGEActorBase, INavmeshObjectMixin):

    def draw(self):
        self.object.draw(logic.RM_TRIS)

    def find_path(self, from_point, to_point):
        return self.object.findPath(from_point, to_point)

    def get_wall_intersection(self, from_point, to_point):
        return self.object.raycast(from_point, to_point)