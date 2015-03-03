from bge import logic, types
from collections import namedtuple
from contextlib import contextmanager

from network.decorators import with_tag
from network.signals import SignalListener
from network.tagged_delegate import FindByTag
from network.logger import logger

from game_system.animation import Animation
from game_system.coordinates import Vector
from game_system.definitions import ComponentLoader, ComponentLoaderResult
from game_system.enums import AnimationMode, AnimationBlend, Axis, CollisionState, PhysicsType
from game_system.signals import CollisionSignal, UpdateCollidersSignal

from functools import partial

from .geometry.mesh.navmesh import BGENavmesh


RayTestResult = namedtuple("RayTestResult", "position normal entity distance")
CollisionResult = namedtuple("CollisionResult", "entity state contacts")
CollisionContact = namedtuple("CollisionContact", "position normal impulse force")


class BGESocket:
    """Attachment socket interface"""

    def __init__(self, name, parent, obj):
        self.name = name
        self._parent = parent
        self._game_object = obj
        self.children = set()


class BGEComponent(FindByTag):
    """Base class for BGE component"""

    subclasses = {}

    def destroy(self):
        """Destroy component"""
        pass

# TODO use enums here

@with_tag("physics")
class BGEPhysicsInterface(BGEComponent):

    # Deprecation warnings
    logger.warning("BGE PhysicsType is not exposed to the PyAPI, defaulting to dynamic collision")
    logger.warning("BGE collision groups are not exposed to the PyAPI")
    logger.warning("BGE collision masks are not exposed to the PyAPI")

    def __init__(self, config_section, entity, obj):
        self._game_object = obj
        self._entity = entity

        self._new_collisions = set()
        self._old_collisions = set()
        self._dispatched = set()
        self._dispatched_entities = set()

        # Physics type
        self._physics_type = PhysicsType.dynamic

        self._has_physics_controller = obj.getPhysicsId() != 0

        if self._has_physics_controller:
            obj.collisionCallbacks.append(self._on_collision)

        # Used for raycast lookups
        obj['physics_component'] = self

    @staticmethod
    def entity_from_object(obj):
        """Returns entity from BGE object

        :param obj: KX_GameObject instance
        """
        try:
            component = obj["physics_component"]

        except KeyError:
            return

        return component._entity

    @property
    def collision_group(self):
        return 0

    @collision_group.setter
    def collision_group(self, group):
        pass

    @property
    def collision_mask(self):
        return 0

    @collision_mask.setter
    def collision_mask(self, mask):
        pass

    @property
    def type(self):
        """The physics type of this object

        :returns: physics type of object, see :py:class:`game_system.enums.PhysicsType`
        """
        return self._physics_type

    @property
    def world_velocity(self):
        if not self._has_physics_controller:
            return Vector()

        return self._game_object.worldLinearVelocity

    @world_velocity.setter
    def world_velocity(self, velocity):
        if not self._has_physics_controller:
            return

        self._game_object.worldLinearVelocity = velocity

    @property
    def world_angular(self):
        if not self._has_physics_controller:
            return Vector()

        return self._game_object.worldLinearVelocity

    @world_angular.setter
    def world_angular(self, velocity):
        if not self._has_physics_controller:
            return

        self._game_object.worldAngularVelocity = velocity

    def ray_test(self, target, source=None, distance=0.0):
        """Perform a ray trace to a target

        :param target: target to trace towards
        :param source: optional origin of trace, otherwise object position
        :param distance: distance to use instead of vector length
        :rtype: :py:class:`bge_game_system.object_types.RayTestResult`
        """
        if source is None:
            source = self._game_object.worldPosition

        result = self._game_object.rayCast(target, source, distance)
        hit_bge_object, hit_position, hit_normal = result

        if not hit_bge_object:
            return

        hit_entity = self.entity_from_object(hit_bge_object)
        hit_distance = (hit_position - source).length

        return RayTestResult(hit_position, hit_normal, hit_entity, hit_distance)

    @staticmethod
    def _convert_contacts(contacts):
        return [CollisionContact(c.hitPosition, c.hitNormal, c.hitImpulse, c.hitForce) for c in contacts]

    def _on_collision(self, other, data=None):
        self._new_collisions.add(other)

        if other in self._dispatched:
            return

        hit_entity = self.entity_from_object(other)

        self._dispatched.add(other)

        if hit_entity:
            self._dispatched_entities.add(hit_entity)

        # Support trunk blender
        if data is None:
            hit_contacts = []

        else:
            hit_contacts = self._convert_contacts(data)

        result = CollisionResult(hit_entity, CollisionState.started, hit_contacts)

        CollisionSignal.invoke(result, target=self._entity)

    @UpdateCollidersSignal.on_global
    def _update_collisions(self):
        # If we have a stored collision
        ended_collisions = self._old_collisions.difference(self._new_collisions)
        self._old_collisions, self._new_collisions = self._new_collisions, set()

        if not ended_collisions:
            return

        callback = CollisionSignal.invoke
        ended_collision = CollisionState.ended

        entity = self._entity
        for obj in ended_collisions:
            self._dispatched.remove(obj)

            if not obj.invalid:
                hit_entity = self.entity_from_object(obj)

                if hit_entity:
                    self._dispatched_entities.remove(hit_entity)

                result = CollisionResult(hit_entity, ended_collision, None)
                callback(result, target=entity)


@with_tag("transform")
class BGETransformInterface(BGEComponent, SignalListener):
    """Physics implementation for BGE entity"""

    def __init__(self, config_section, entity, obj):
        self._game_object = obj
        self._entity = entity

        self._parent = None
        self.children = set()
        self.sockets = self.create_sockets(self._game_object)

        self.register_signals()

    @property
    def parent(self):
        return self._parent

    @parent.setter
    def parent(self, parent):
        if parent is self._parent:
            return

        self._parent.children.remove(self._entity)
        self._game_object.removeParent()

        if parent is None:
            return

        if not hasattr(parent, "_obj"):
            raise TypeError("Invalid parent type {}".format(parent.__class__.__name__))

        self._game_object.setParent(parent._obj)
        parent.children.add(self._entity)
        self._parent = parent

    @property
    def world_position(self):
        return self._game_object.worldPosition

    @world_position.setter
    def world_position(self, position):
        self._game_object.worldPosition = position

    @property
    def world_orientation(self):
        return self._game_object.worldOrientation.to_euler()

    @world_orientation.setter
    def world_orientation(self, orientation):
        self._game_object.worldOrientation = orientation

    @property
    def is_colliding(self):
        return bool(self._dispatched)

    def align_to(self, vector, factor=1, axis=Axis.y):
        """Align object to vector

        :param vector: direction vector
        :param factor: slerp factor
        :param axis: alignment direction
        """
        if not vector.length_squared:
            return

        forward_axis = Axis[axis].upper()

        rotation_quaternion = vector.to_track_quat(forward_axis, "Z")
        current_rotation = self.world_orientation.to_quaternion()
        self.world_orientation = current_rotation.slerp(rotation_quaternion, factor).to_euler()

    def create_sockets(self, obj):
        sockets = set()
        for obj in obj.childrenRecursive:
            socket_name = obj.get("socket")
            if not socket_name:
                continue

            socket = BGESocket(socket_name, self, obj)
            sockets.add(socket)

        return sockets

    def get_direction_vector(self, axis):
        """Get the axis vector of this object in world space

        :param axis: :py:class:`bge_game_system.enums.Axis` value
        :rtype: :py:class:`mathutils.Vector`
        """
        vector = [0, 0, 0]
        vector[axis] = 1

        return Vector(self.object.getAxisVect(vector))

    def is_colliding_with(self, entity):
        """Determines if the entity is colliding with another entity

        :param entity: entity to __call__
        :returns: result of condition
        """
        return entity in self._dispatched_entities


@with_tag("animation")
class BGEAnimationInterface(BGEComponent):
    """Animation implementation for BGE entity"""

    def __init__(self, config_section, entity, obj):
        try:
            skeleton = next(o for o in obj.childrenRecursive if isinstance(obj, types.BL_ArmatureObject))

        except StopIteration:
            raise TypeError("Animation component requires Armature object")

        self._game_object = skeleton

        # Define conversions from Blender behaviours to Network animation enum
        self._bge_play_constants = {AnimationMode.play: logic.KX_ACTION_MODE_PLAY,
                                    AnimationMode.loop: logic.KX_ACTION_MODE_LOOP,
                                    AnimationMode.ping_pong: logic.KX_ACTION_MODE_PING_PONG}

        self._bge_blend_constants = {AnimationBlend.interpolate: logic.KX_ACTION_BLEND_BLEND,
                                     AnimationBlend.add: logic.KX_ACTION_BLEND_ADD}

        self.animations = self.create_animations(skeleton, config_section)

    @staticmethod
    def create_animations(obj, data):
        animations = {}

        for animation_name, animation_data in data.items():
            frame_info = animation_data['frame_info']
            start = frame_info['start']
            end = frame_info['end']

            modes = animation_data['modes']
            blend_mode = modes['blend']
            play_mode = modes['play']

            layer_data = animation_data['layers']
            layer = layer_data['layer']
            blending = layer_data['blending']
            weight = layer_data['weight']

            playback = animation_data['playback']
            priority = playback['priority']
            speed = playback['speed']

            callback = partial(obj.isPlayingAction, layer)

            animation = Animation(animation_name, start, end, layer, priority, blending, play_mode, weight, speed,
                                  blend_mode, callback)
            animations[animation_name] = animation

        return animations

    def get_frame(self, animation):
        """Get the current frame of the animation

        :param animation: animation object
        """
        return int(self._game_object.getActionFrame(animation.layer))

    def play(self, animation):
        """Play animation on bound object

        :param animation: animation resource
        """
        play_mode = self._bge_play_constants[animation.mode]
        blend_mode = self._bge_blend_constants[animation.blend_mode]
        self._game_object.playAction(animation.name, animation.start, animation.end, animation.layer, animation.priority,
                             animation.blend, play_mode, animation.weight, speed=animation.speed, blend_mode=blend_mode)

    def stop(self, animation):
        """Stop a playing animation on bound object

        :param animation: animation resource
        """
        self._game_object.stopAction(animation.layer)


@with_tag("camera")
class BGECameraInterface(BGEComponent):

    def __init__(self, config_section, entity, obj):
        self._game_object = obj

    @contextmanager
    def active_context(self):
        camera = self._game_object
        scene = camera.scene

        old_camera = scene.active_camera
        scene.active_camera = camera

        yield

        if old_camera:
            scene.active_camera = old_camera

    def is_point_in_frustum(self, point):
        """Determine if a point resides in the camera frustum

        :param point: :py:class:`mathutils.Vector`
        :rtype: bool
        """
        return self._game_object.pointInsideFrustum(point)

    def is_sphere_in_frustum(self, point, radius):
        """Determine if a sphere resides in the camera frustum

        :param point: :py:class:`mathutils.Vector`
        :param radius: radius of sphere
        :rtype: bool
        """
        return self._game_object.sphereInsideFrustum(point, radius) != self._game_object.OUTSIDE

    def get_screen_direction(self, x=0.5, y=0.5):
        """Find direction along screen vector

        :param x: screen space x coordinate
        :param y: screen space y coordinate
        """
        return self._game_object.getScreenRay(x, y)


@with_tag("lamp")
class BGELampInterface(BGEComponent):

    def __init__(self, config_section, entity, obj):
        self._game_object = obj

    @property
    def colour(self):
        return self._game_object.color

    @colour.setter
    def colour(self, colour):
        self._game_object.color = colour

    @property
    def intensity(self):
        return self._game_object.energy

    @intensity.setter
    def intensity(self, energy):
        self._game_object.energy = energy


@with_tag("navmesh")
class BGENavmeshInterface(BGEComponent):

    def __init__(self, config_section, entity, obj):
        self._navmesh = BGENavmesh(obj)
        self._game_object = obj

        self.find_node = self._navmesh.find_node
        self.nodes = self._navmesh.polygons


@with_tag("BGE")
class BGEComponentLoader(ComponentLoader):

    def __init__(self, *component_tags):
        self.component_tags = component_tags
        self.component_classes = {tag: BGEComponent.find_subclass_for(tag) for tag in component_tags}

    @classmethod
    def create_object(cls, config_parser):
        scene = logic.getCurrentScene()

        object_name = config_parser['object_name']
        assert object_name in scene.objectsInactive, (object_name, scene.objectsInactive)
        return scene.addObject(object_name, object_name)

    def load(self, entity, config_parser):
        obj = self.create_object(config_parser)
        components = self._load_components(config_parser, entity, obj)
        return BGEComponentLoaderResult(components, obj)

    def unload(self, loader_result):
        for component in loader_result.components.values():
            component.destroy()

        game_object = loader_result.game_object
        if not game_object.invalid:
            game_object.endObject()


class BGEComponentLoaderResult(ComponentLoaderResult):

    def __init__(self, components, obj):
        self.game_object = obj
        self.components = components