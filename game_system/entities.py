from functools import partial

from network.decorators import requires_netmode, simulated
from network.descriptors import Attribute
from network.enums import Netmodes, Roles
from network.utilities import mean
from network.replicable import Replicable
from network.signals import SignalListener
from network.world_info import WorldInfo
from .configobj import ConfigObj
from .coordinates import Vector, Euler
from .definitions import ComponentLoader
from .enums import Axis, CameraMode, CollisionGroups, CollisionState
from .pathfinding.algorithm import AStarAlgorithm, FunnelAlgorithm
from .resources import ResourceManager
from .signals import ActorDamagedSignal, CollisionSignal, LogicUpdateSignal, PhysicsReplicatedSignal


class ComponentEntity:
    """Base class for handling game engine specific system components"""

    component_tags = []
    definition_name = "definition.cfg"

    _definitions = {}

    def unload_components(self):
        """Unloads entity components
        """

        try:
            result = self._component_result

        except AttributeError as err:
            raise AttributeError("Components have not been loaded yet") from err

        result.unload()

    def load_components(self):
        """Loads entity-specific components marked using the with_tag system/

        Uses an abstract ComponentLoader to read a configuration file providing loader data
        """
        self_class = self.__class__

        # Lazy load component loader
        try:
            component_loader = self_class._component_loader

            if component_loader.component_tags != self_class.component_tags:
                raise AttributeError("Mismatch in component tags, reloading")

        except AttributeError:
            component_loader = ComponentLoader(*self_class.component_tags)
            self_class._component_loader = component_loader

        class_name = self_class.__name__
        definitions = self_class._definitions

        # Lazy load definitions
        try:
            platform_definition = definitions[class_name]

        except KeyError:
            resources = ResourceManager[class_name]
            platform = ResourceManager.environment

            try:
                definition = resources[self_class.definition_name]

            except TypeError:
                raise FileNotFoundError("Could not find definition file for {}".format(class_name))

            full_path = ResourceManager.get_absolute_path(definition)

            definition_sections = ConfigObj(full_path)
            platform_definition = definition_sections[platform]
            definitions[class_name] = platform_definition

        component_result = component_loader.load(self, platform_definition)

        # Load components
        for component_tag, component in component_result.components.items():
            setattr(self, component_tag, component)

        self._component_result = component_result


class Actor(ComponentEntity, Replicable):
    """Physics enabled network object"""

    component_tags = ("physics", "transform")

    # Network data
    network_position = Attribute(data_type=Vector)
    network_velocity = Attribute(Vector())
    network_orientation = Attribute(data_type=Euler, notify=True)
    network_angular = Attribute(Vector(), notify=True)
    network_collision_group = Attribute(data_type=int, notify=True)
    network_collision_mask = Attribute(data_type=int, notify=True)
    network_replication_time = Attribute(data_type=float, notify=True)
    roles = Attribute(Roles(Roles.authority, Roles.simulated_proxy), notify=True)

    # Replicated physics parameters
    MAX_POSITION_DIFFERENCE_SQUARED = 4
    POSITION_CONVERGE_FACTOR = 0.6

    # Default settings
    always_relevant = False
    replicate_physics_to_owner = False
    replicate_simulated_physics = True

    def conditions(self, is_owner, is_complaint, is_initial):
        yield from super().conditions(is_owner, is_complaint, is_initial)

        remote_role = self.roles.remote

        # If simulated, send rigid body state
        valid_role = (remote_role == Roles.simulated_proxy)
        owner_accepts_physics = self.replicate_physics_to_owner or not is_owner
        allowed_physics = self.replicate_simulated_physics and owner_accepts_physics and not self.transform.parent

        if (valid_role and allowed_physics) or is_initial:
            yield "network_position"
            yield "network_orientation"
            yield "network_angular"
            yield "network_velocity"
            yield "network_collision_group"
            yield "network_collision_mask"
            yield "network_replication_time"

    def copy_state_to_network(self):
        """Copies Physics State to network attributes"""
        self.network_position = self.transform.world_position.copy()
        self.network_orientation = self.transform.world_orientation.copy()
       # self.network_angular = self.physics.world_angular.copy()
        #self.network_velocity = self.physics.world_velocity.copy()
        #self.network_collision_group = self.physics.collision_group
        #self.network_collision_mask = self.physics.collision_mask
        self.network_replication_time = WorldInfo.elapsed

    def on_initialised(self):
        super().on_initialised()

        self.load_components()

        self.camera_radius = 1.0
        self.indestructible = False

    def on_deregistered(self):
        self.unload_components()

        super().on_deregistered()

    def on_notify(self, name):
        if name == "network_collision_group":
            pass#self.physics.collision_group = self.network_collision_group

        elif name == "network_collision_mask":
            pass#self.physics.collision_mask = self.network_collision_mask

        elif name == "network_angular":
            self.physics.world_angular = self.network_angular

        elif name == "network_replication_time":
            print(self.network_position)
            PhysicsReplicatedSignal.invoke(self.network_replication_time, target=self)

        else:
            super().on_notify(name)


class Camera(Actor):

    component_tags = Actor.component_tags + ("camera",)

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
            return self.camera.is_point_in_frustum(actor.world_position)

        return self.camera.is_sphere_in_frustum(actor.world_position, radius)


class Navmesh(Actor):

    component_tags = Actor.component_tags + ("navmesh",)

    roles = Attribute(Roles(Roles.authority, Roles.none))

    def on_initialised(self):
        super().on_initialised()

        self.find_node = self.navmesh.find_node
        self.find_low_resolution_path = AStarAlgorithm().find_path
        self.find_high_resolution_path = partial(FunnelAlgorithm().find_path, nodes=self.navmesh.nodes)


class Pawn(Actor):

    component_tags = Actor.component_tags + ("animation",)

    # Network Attributes
    alive = Attribute(True, notify=True, complain=True)
    flash_count = Attribute(0)
    health = Attribute(100, notify=True, complain=True)
    info = Attribute(data_type=Replicable, complain=True)
    roles = Attribute(Roles(Roles.authority, Roles.autonomous_proxy), notify=True)
    view_pitch = Attribute(0.0)

    FLOOR_OFFSET = 2.2

    @property
    def on_ground(self):
        downwards = -self.physics.get_direction(Axis.z)
        target = self.transform.world_position + downwards
        trace = self.physics.ray_test(target, distance=self.__class__.FLOOR_OFFSET + 0.5)
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

    def on_initialised(self):
        super().on_initialised()

        self.weapon_attachment = None

        # Non owner attributes
        self.last_flash_count = 0

        self.walk_speed = 4.0
        self.run_speed = 7.0
        self.turn_speed = 1.0
        self.replication_update_period = 1 / 60

        # self.behaviours = BehaviourTree(self)
        # self.behaviours.blackboard['pawn'] = self

        self.playing_animations = {}

    @ActorDamagedSignal.on_context
    def take_damage(self, damage, instigator, hit_position, momentum):
        self.health = int(max(self.health - damage, 0))

    @simulated
    @LogicUpdateSignal.on_global
    def update(self, delta_time):
        # Allow remote players to determine if we are alive without seeing health
        self.update_alive_status()
        # self.behaviours.update()

    def update_alive_status(self):
        """Update health boolean.

        Runs on authority / autonomous proxy only
        """
        self.alive = self.health > 0


class Particle(ComponentEntity, SignalListener):

    component_tags = ("physics", "transform")

    def __init__(self):
        self.register_signals()
        self.on_initialised()

    def delete(self):
        self.unregister_signals()


class Projectile(Actor):

    def on_registered(self):
        super().on_registered()

        self.replicate_temporarily = True
        self.in_flight = True

        self.collision_group = CollisionGroups.projectile
        self.collision_mask = CollisionGroups.pawn | CollisionGroups.geometry

    @CollisionSignal.on_context
    @simulated
    def on_collision(self, collision_result):
        if not (collision_result.state == CollisionState.started and self.in_flight):
            return

        if isinstance(collision_result.entity, Pawn):
            self.server_deal_damage(collision_result)

        self.deregister()
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
        hit_normal = mean(c.normal for c in collision_result.contacts).normalized()
        hit_position = mean(c.position for c in collision_result.contacts)
        hit_velocity = self.physics.world_velocity.dot(hit_normal) * hit_normal
        hit_momentum = self.mass * hit_velocity

        ActorDamagedSignal.invoke(weapon.base_damage, instigator, hit_position, hit_momentum,
                                  target=collision_result.entity)


class WeaponAttachment(Actor):

    roles = Attribute(Roles(Roles.authority, Roles.none))

    def on_initialised(self):
        super().on_initialised()

        self.replicate_simulated_physics = False

    def play_fire_effects(self):
        pass
