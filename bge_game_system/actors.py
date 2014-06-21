from functools import partial

from network.decorators import requires_netmode, simulated
from network.descriptors import Attribute
from network.enums import Netmodes, Roles
from network.replicable import Replicable
from network.world_info import WorldInfo

from game_system.resources import ResourceManager
from game_system.signals import *
from game_system.enums import *
from game_system.animation import Animation
from game_system.ai.behaviour_tree import BehaviourTree
from game_system.timer import Timer
from game_system.math import mean

from .types.objects import BGEActorBase, BGECameraBase, BGELampBase, BGENavmeshBase, BGEPawnBase

from mathutils import Euler, Vector


__all__ = ["Actor", "Camera", "Lamp", "Pawn", "WeaponAttachment"]


class Actor(BGEActorBase, Replicable):
    """Physics enabled network object"""

    # Physics data
    _position = Attribute(type_of=Vector, notify=True)
    _rotation = Attribute(type_of=Euler, notify=True)
    _angular = Attribute(type_of=Vector, notify=True)
    _velocity = Attribute(type_of=Vector, notify=True)
    _collision_group = Attribute(type_of=int, notify=True)
    _collision_mask = Attribute(type_of=int, notify=True)
    _replication_time = Attribute(type_of=float)

    roles = Attribute(Roles(Roles.authority, Roles.simulated_proxy), notify=True)

    # Replicated physics parameters
    MAX_POSITION_DIFFERENCE_SQUARED = 4
    POSITION_CONVERGE_FACTOR = 0.6

    @property
    def lifespan(self):
        return self._lifespan_timer.value

    @lifespan.setter
    def lifespan(self, value):
        self._lifespan_timer.reset()
        self._lifespan_timer.end = value

    @property
    def resources(self):
        return ResourceManager[self.__class__.__name__]

    def conditions(self, is_owner, is_complaint, is_initial):
        yield from super().conditions(is_owner, is_complaint, is_initial)

        remote_role = self.roles.remote

        # If simulated, send rigid body state
        valid_role = (remote_role == Roles.simulated_proxy)
        owner_accepts_physics = self.replicate_physics_to_owner or not is_owner
        allowed_physics = self.replicate_simulated_physics and owner_accepts_physics and not self.parent

        if (valid_role and allowed_physics) or is_initial:
            yield "_position"
            yield "_rotation"
            yield "_angular"
            yield "_velocity"
            yield "_collision_group"
            yield "_collision_mask"
            yield "_replication_time"

    def copy_state_to_network(self):
        """Copies Physics State to network attributes"""
        self._position = self.world_position.copy()
        self._angular = self.world_angular.copy()
        self._velocity = self.world_velocity.copy()
        self._rotation = self.world_rotation.copy()
        self._collision_group = self.collision_group
        self._collision_mask = self.collision_mask
        self._replication_time = WorldInfo.elapsed

    def on_initialised(self):
        super().on_initialised()

        self.camera_radius = 1.0
        self.indestructable = False

        self.always_relevant = False
        self.replicate_physics_to_owner = True
        self.replicate_simulated_physics = True

        self._lifespan_timer = Timer(active=False)
        self._lifespan_timer.on_target = self.request_unregistration

    def on_unregistered(self):
        # Unregister any actor children
        for child in self.children:
            if isinstance(child, Actor) and child.indestructable:
                continue

            child.request_unregistration()

        super().on_unregistered()

    @simulated
    def on_replicated_physics(self, position, velocity, timestamp):
        """Callback when physics is replicated

        :param position: current replicated position
        :param velocity: current replicated velocity
        :param timestamp: time of data transmission
        """
        PhysicsReplicatedSignal.invoke(timestamp, position, velocity, target=self)

    def on_notify(self, name):
        if name == "_collision_group":
            self.collision_group = self._collision_group
        elif name == "_collision_mask":
            self.collision_mask = self._collision_mask
        elif name == "_angular":
            self.world_angular = self._angular
        elif name == "_rotation":
            self.world_rotation = self._rotation
        elif name == "_position":
            #self.on_replicated_physics(self._position, self._velocity, self._replication_time)
            self.world_position = self._position
        else:
            super().on_notify(name)


class Camera(BGECameraBase, Actor):

    entity_name = "Camera"

    roles = Attribute(Roles(Roles.authority, Roles.autonomous_proxy), notify=True)

    @property
    def mode(self):
        return self._mode

    @mode.setter
    def mode(self, mode):
        if mode == self._mode:
            return

        self._mode = mode

        if mode == CameraMode.first_person:
            self.local_position = Vector()

        elif mode == CameraMode.third_person:
            self.local_position = Vector((0, -self.gimbal_offset, 0))

        self.local_rotation = Euler()

    def draw(self):
        """Draws a colourful 3D camera object to the screen"""
        raise NotImplementedError()

    def on_initialised(self):
        super().on_initialised()

        self._mode = None

        self.gimbal_offset = 2.0
        self.mode = CameraMode.first_person

    def sees_actor(self, actor):
        """Determine if actor is visible to camera

        :param actor: Actor subclass
        :rtype: bool
        """
        radius = actor.camera_radius

        if radius < 0.5:
            return self.is_point_in_frustum(actor.world_position)

        return self.is_sphere_in_frustum(actor.world_position, radius)

    @LogicUpdateSignal.global_listener
    @simulated
    def update(self, delta_time):
        if self.visible:
            self.draw()


class Pawn(BGEPawnBase, Actor):
    # Network Attributes
    alive = Attribute(True, notify=True, complain=True)
    flash_count = Attribute(0)
    health = Attribute(100, notify=True, complain=True)
    info = Attribute(type_of=Replicable, complain=True)
    roles = Attribute(Roles(Roles.authority, Roles.autonomous_proxy), notify=True)
    view_pitch = Attribute(0.0)
    weapon_attachment_class = Attribute(type_of=type(Replicable), notify=True, complain=True)

    FLOOR_OFFSET = 2.2

    @property
    def on_ground(self):
        downwards = -self.get_direction(Axis.z)
        trace = self.trace_ray(self.world_position + downwards, distance=self.__class__.FLOOR_OFFSET + 0.5)
        return trace is not None

    def conditions(self, is_owner, is_complaint, is_initial):
        yield from super().conditions(is_owner, is_complaint, is_initial)

        # Only non-owners need this
        if not is_owner:
            yield "view_pitch"
            yield "flash_count"

        # These will be explicitly set
        if is_complaint:
            yield "weapon_attachment_class"
            yield "alive"
            yield "info"

            # Prevent cheating
            if is_owner:
                yield "health"

    @simulated
    def create_weapon_attachment(self, cls):
        self.weapon_attachment = cls()
        self.weapon_attachment.set_parent(self, "weapon")

        if self.weapon_attachment is not None:
            self.weapon_attachment.unpossessed()

        self.weapon_attachment.possessed_by(self)

        self.weapon_attachment.local_position = Vector()
        self.weapon_attachment.local_rotation = Euler()

    def on_initialised(self):
        super().on_initialised()

        self.weapon_attachment = None

        # Non owner attributes
        self.last_flash_count = 0

        self.walk_speed = 4.0
        self.run_speed = 7.0
        self.turn_speed = 1.0
        self.replication_update_period = 1 / 60

        self.behaviours = BehaviourTree(self)
        self.behaviours.blackboard['pawn'] = self

        self.playing_animations = {}

    @simulated
    def on_notify(self, name):
        # play weapon effects
        if name == "weapon_attachment_class":
            self.create_weapon_attachment(self.weapon_attachment_class)

        else:
            super().on_notify(name)

    @simulated
    def play_animation(self, name, start, end, layer=0, priority=0, blend=0.0, mode=AnimationMode.play, weight=0.0,
                       speed=1.0, blend_mode=AnimationBlend.interpolate):
        """See :py:class:`bge_game_system.object_types.BGEAnimatedObject`"""
        super().play_animation(name, start, end, layer, priority, blend, mode, weight, speed, blend_mode)

        is_playing_callback = partial(self.is_playing_animation, layer)
        self.playing_animations[layer] = Animation(name, start, end, layer, priority, blend, mode, weight, speed,
                                                   is_playing_callback)

    @simulated
    def stop_animation(self, layer=0):
        """Stop playing a skeletal animation for layer

        :param layer: layer currently playing animation
        """
        super().stop_animation(layer)

        self.playing_animations.pop(layer)

    @ActorDamagedSignal.listener
    def take_damage(self, damage, instigator, hit_position, momentum):
        self.health = int(max(self.health - damage, 0))

    @simulated
    @LogicUpdateSignal.global_listener
    def update(self, delta_time):
        if self.weapon_attachment:
            self.update_weapon_attachment()

        # Allow remote players to determine if we are alive without seeing health
        self.update_alive_status()
        self.behaviours.update()
        self.update_animation_info()

    def update_alive_status(self):
        """Update health boolean
        Runs on authority / autonomous proxy only"""
        self.alive = self.health > 0

    @simulated
    def update_animation_info(self):
        """Updates record of playing animations"""
        for layer, animation in self.playing_animations.items():
            if not animation.playing:
                self.skeleton.stop_animation(layer)

    @simulated
    def update_weapon_attachment(self):
        # Account for missing shots
        if self.flash_count != self.last_flash_count:
            # Protect from wrap around
            if self.last_flash_count > self.flash_count:
                self.last_flash_count = -1

            self.weapon_attachment.play_fire_effects()
            self.last_flash_count += 1

        self.weapon_attachment.local_rotation = Euler((self.view_pitch, 0, 0))


class Lamp(BGELampBase, Actor):
    roles = Roles(Roles.authority, Roles.simulated_proxy)

    entity_name = "Lamp"

    def on_initialised(self):
        super().on_initialised()

        self._intensity = self.intensity

    @property
    def active(self):
        return bool(self.intensity)

    @active.setter
    def active(self, state):
        """Modifiy the lamp active state by setting the intensity to a placeholder

        :param state: new active state
        """

        if state == self._intensity:
            return

        if state:
            self._intensity, self.intensity = 0.0, self._intensity

        else:
            self._intensity, self.intensity = self.intensity, 0.0


class Navmesh(BGENavmeshBase, Actor):
    roles = Roles(Roles.authority, Roles.none)

    entity_name = "Navmesh"


class Projectile(Actor):

    def on_registered(self):
        super().on_registered()

        self.replicate_temporarily = True
        self.in_flight = True

        self.collision_group = CollisionGroups.projectile
        self.collision_mask = CollisionGroups.pawn | CollisionGroups.geometry

    @CollisionSignal.listener
    @simulated
    def on_collision(self, collision_result):
        if not (collision_result.collision_type == CollisionType.started and self.in_flight):
            return

        if isinstance(collision_result.hit_object, Pawn):
            self.server_deal_damage(collision_result)

        self.request_unregistration()
        self.in_flight = False

    @requires_netmode(Netmodes.server)
    def server_deal_damage(self, collision_result):
        weapon = self.owner

        # If the weapon disappears before projectile
        if not weapon:
            return

        # Get weapon's owner (controller)
        instigator = weapon.owner

        # Calculate hit information
        hit_normal = mean(c.hit_normal for c in collision_result.hit_contacts).normalized()
        hit_position = mean(c.hit_position for c in collision_result.hit_contacts)
        hit_velocity = self.world_velocity.dot(hit_normal) * hit_normal
        hit_momentum = self.mass * hit_velocity

        ActorDamagedSignal.invoke(weapon.base_damage, instigator, hit_position, hit_momentum,
                                  target=collision_result.hit_object)


class WeaponAttachment(Actor):

    roles = Attribute(Roles(Roles.authority, Roles.none))

    def on_initialised(self):
        super().on_initialised()

        self.replicate_simulated_physics = False

    def play_fire_effects(self):
        pass