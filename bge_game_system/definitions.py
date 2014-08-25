from bge import logic
from collections import namedtuple
from contextlib import contextmanager

from network.decorators import with_tag
from network.signals import SignalListener
from network.tagged_delegate import FindByTag

from game_system.definitions import ComponentLoader
from game_system.enums import AnimationMode, AnimationBlend, CollisionType, PhysicsType
from game_system.signals import CollisionSignal, UpdateCollidersSignal


RayTestResult = namedtuple("RayTestResult", "hit_position hit_normal hit_object distance")
CollisionResult = namedtuple("CollisionResult", "hit_object collision_type hit_contacts")
CollisionContact = namedtuple("CollisionContact", "hit_position hit_normal hit_impulse hit_force")


def documentation():
    return """
    The environment specified by ResourceManager.environment is used to select the appropriate ComponentLoader for the
    current game engine

    Each component that belongs to this definition can be selected by a tag i.e "physics" and these are specified in
    the appropriate base classes for cameras, pawns etc, by instantiating a loader with the tags as arguments

    class Pawn:
        component_loader = ComponentLoader("physics", "animation")

    Each component is provided a configuration section which pertains to the section within a config file

    [BGE]
        [physics]
            velocity = 1.0
            range = 2.0

    This file is only used to load platform-specific data (like mesh names)

    """


class BGEComponent(FindByTag):
    subclasses = {}


@with_tag("physics")
class BGEPhysicsInterface(BGEComponent, SignalListener):
    """Physics implementation for BGE entity"""

    def __init__(self, config_section, entity, obj):
        self._obj = obj
        self._entity = entity

        # Used for raycast lookups
        obj['physics_component'] = self

        # Physics type
        physics_constants = {logic.KX_PHYSICS_STATIC: PhysicsType.static,
                            logic.KX_PHYSICS_DYNAMIC: PhysicsType.dynamic,
                            logic.KX_PHYSICS_RIGID_BODY: PhysicsType.rigid_body,
                            logic.KX_PHYSICS_SOFT_BODY: PhysicsType.soft_body,
                            logic.KX_PHYSICS_OCCLUDER: PhysicsType.occluder,
                            logic.KX_PHYSICS_SENSOR: PhysicsType.sensor,
                            logic.KX_PHYSICS_NAVIGATION_MESH: PhysicsType.navigation_mesh,
                            logic.KX_PHYSICS_CHARACTER: PhysicsType.character,
                            logic.KX_PHYSICS_NO_COLLISION: PhysicsType.no_collision}

        if getattr(obj, "meshes", None):
            self._physics_type = physics_constants[obj.physicsType]

        else:
            self._physics_type = PhysicsType.no_collision

        # Collisions
        if not self._physics_type in (PhysicsType.navigation_mesh, PhysicsType.no_collision):
            obj.collisionCallbacks.append(self._on_collision)

        self._new_collisions = set()
        self._old_collisions = set()
        self._dispatched = set()
        self._dispatched_entities = set()

        self.register_signals()

    @staticmethod
    def entity_from_object(obj):
        try:
            component = obj["physics_component"]

        except KeyError:
            return

        return component._entity

    @property
    def physics(self):
        """The physics type of this object

        :returns: physics type of object, see :py:class:`bge_game_system.enums.PhysicsType`
        """
        return self._physics_type

    @property
    def world_position(self):
        return self._obj.worldPosition

    @world_position.setter
    def world_position(self, position):
        self._obj.worldPosition = position

    @property
    def world_velocity(self):
        return self._obj.worldLinearVelocity

    @world_velocity.setter
    def world_velocity(self, velocity):
        self._obj.worldLinearVelocity = velocity

    @property
    def world_orientation(self):
        return self._obj.worldOrientation.to_euler()

    @world_orientation.setter
    def world_orientation(self, orientation):
        self._obj.worldOrientation = orientation

    @property
    def is_colliding(self):
        return bool(self._dispatched)

    def is_colliding_with(self, entity):
        """Determines if the entity is colliding with another entity

        :param entity: entity to evaluate
        :returns: result of condition
        """
        return entity in self._dispatched_entities

    @staticmethod
    def _convert_contacts(contacts):
        return [CollisionContact(c.hitPosition, c.hitNormal, c.hitImpulse, c.hitForce) for c in contacts]

    def _on_collision(self, other, data):
        self._new_collisions.add(other)

        if other in self._dispatched:
            return

        hit_entity = self.entity_from_object(other)

        self._dispatched.add(other)

        if hit_entity:
            self._dispatched_entities.add(hit_entity)

        hit_contacts = self._convert_contacts(data)
        result = CollisionResult(hit_entity, CollisionType.started, hit_contacts)

        CollisionSignal.invoke(result, target=self._entity)

    @UpdateCollidersSignal.global_listener
    def _update_collisions(self):
        # If we have a stored collision
        ended_collisions = self._old_collisions.difference(self._new_collisions)
        self._old_collisions, self._new_collisions = self._new_collisions, set()

        if not ended_collisions:
            return

        callback = CollisionSignal.invoke
        ended_collision = CollisionType.ended

        entity = self._entity
        for obj in ended_collisions:
            self._dispatched.remove(obj)

            if not obj.invalid:
                hit_entity = self.entity_from_object(obj)

                if hit_entity:
                    self._dispatched_entities.remove(hit_entity)

                result = CollisionResult(hit_entity, ended_collision, None)
                callback(result, target=entity)

    def ray_test(self, target, source=None, distance=0.0):
        """Perform a ray trace to a target

        :param target: target to trace towards
        :param source: optional origin of trace, otherwise object position
        :param distance: distance to use instead of vector length
        :rtype: :py:class:`bge_game_system.object_types.RayTestResult`
        """
        if source is None:
            source = self._obj.worldPosition

        result = self._obj.rayCast(target, source, distance)

        if not any(result):
            return None

        hit_bge_object, hit_position, hit_normal = result
        hit_object = self.entity_from_object(hit_bge_object)
        hit_distance = (hit_position - source).length

        return RayTestResult(hit_position, hit_normal, hit_object, hit_distance)


@with_tag("animation")
class BGEAnimationInterface(BGEComponent):
    """Animation implementation for BGE entity"""

    def __init__(self, config_secton, entity, obj):
        self._obj = obj

        # Define conversions from Blender behaviours to Network animation enum
        self._bge_play_constants = {AnimationMode.play: logic.KX_ACTION_MODE_PLAY,
                                    AnimationMode.loop: logic.KX_ACTION_MODE_LOOP,
                                    AnimationMode.ping_pong: logic.KX_ACTION_MODE_PING_PONG}

        self._bge_blend_constants = {AnimationBlend.interpolate: logic.KX_ACTION_BLEND_BLEND,
                                     AnimationBlend.add: logic.KX_ACTION_BLEND_ADD}

    def get_animation_frame(self, animation):
        """Get the current frame of the animation

        :param animation: animation object
        """
        return int(self._obj.getActionFrame(animation.layer))

    def play_animation(self, animation):
        """Play animation on bound object

        :param animation: animation resource
        """
        play_mode = self._bge_play_constants[animation.mode]
        blend_mode = self._bge_blend_constants[animation.blend_mode]
        self._obj.playAction(animation.name, animation.start, animation.end, animation.layer, animation.priority,
                             animation.blend, play_mode, animation.weight, speed=animation.speed, blend_mode=blend_mode)

    def stop_animation(self, animation):
        """Stop a playing animation on bound object

        :param animation: animation resource
        """
        self._obj.stopAction(animation.layer)

    def is_playing(self, animation):
        """Determine if playing animation on bound object

        :param animation: animation resource
        """
        return self._obj.isPlayingAction(animation.layer)


@with_tag("camera")
class BGECameraInterface(BGEComponent):

    def __init__(self, config_section, entity, obj):
        self._obj = obj

    @contextmanager
    def active_context(self):
        camera = self._obj
        scene = camera.scene

        old_camera = scene.active_camera
        scene.active_camera = camera

        yield

        if old_camera:
            scene.active_camera = old_camera

    def is_point_in_frustum(self, point):
        """Determine if a point resides in the camera frustum

        :param point: :py:code:`mathutils.Vector`
        :rtype: bool
        """
        return self._obj.pointInsideFrustum(point)

    def is_sphere_in_frustum(self, point, radius):
        """Determine if a sphere resides in the camera frustum

        :param point: :py:code:`mathutils.Vector`
        :param radius: radius of sphere
        :rtype: bool
        """
        return self._obj.sphereInsideFrustum(point, radius) != self._obj.OUTSIDE

    def get_screen_direction(self, x=0.5, y=0.5):
        """Find direction along screen vector

        :param x: screen space x coordinate
        :param y: screen space y coordinate
        """
        return self._obj.getScreenRay(x, y)


@with_tag("lamp")
class BGELampInterface(BGEComponent):

    def __init__(self, config_section, entity, obj):
        self._obj = obj

    @property
    def intensity(self):
        return self._obj.energy

    @intensity.setter
    def intensity(self, energy):
        self._obj.energy = energy


@with_tag("navmesh")
class BGENavmeshInterface(BGEComponent):

    def __init__(self, config_section, entity, obj):
        self._obj = obj

    def draw(self):
        self._obj.draw(logic.RM_TRIS)

    def find_path(self, from_point, to_point):
        return self._obj.findPath(from_point, to_point)

    def get_wall_intersection(self, from_point, to_point):
        return self._obj.raycast(from_point, to_point)


@with_tag("BGE")
class BGEComponentLoader(ComponentLoader):

    def __init__(self, *component_tags):
        self.component_classes = {tag: BGEComponent.find_subclass_for(tag) for tag in component_tags}

    def load_components(self, entity, config_parser):
        scene = logic.getCurrentScene()

        object_name = config_parser['object_name']
        obj = scene.addObject(object_name, object_name)

        return self._load_components(config_parser, entity, obj)
