from network.decorators import requires_netmode
from network.descriptors import Attribute, TypeFlag, MarkAttribute
from network.enums import Netmodes, Roles
from network.replicable import Replicable
from network.world_info import WorldInfo

from mathutils import Vector

from .object_types import *
from .resources import ResourceManager
from .signals import *
from .utilities import square_falloff

__all__ = ['Weapon', 'TraceWeapon', 'ProjectileWeapon', 'EmptyWeapon']


class Weapon(Replicable):
    roles = Attribute(Roles(Roles.authority, Roles.autonomous_proxy))
    ammo = Attribute(70, notify=True)

    @property
    def can_fire(self):
        return (bool(self.ammo) and (WorldInfo.tick - self.last_fired_tick) >= (self.shoot_interval *
                                                                                WorldInfo.tick_rate))

    @property
    def resources(self):
        return ResourceManager.load_resource(self.__class__.__name__)

    @property
    def shoot_sound(self):
        return "shoot.mp3"

    @property
    def icon_path(self):
        return "icon.tga"

    def consume_ammo(self):
        self.ammo -= 1

    def fire(self, camera):
        self.consume_ammo()
        self.last_fired_tick = WorldInfo.tick

    def conditions(self, is_owner, is_complaint, is_initial):
        yield from super().conditions(is_owner, is_complaint, is_initial)

        yield "ammo"

    def on_initialised(self):
        super().on_initialised()

        self.shoot_interval = 0.5
        self.last_fired_tick = 0
        self.max_ammo = 70

        self.momentum = 1
        self.maximum_range = 20
        self.effective_range = 10
        self.base_damage = 40

        self.attachment_class = None


class TraceWeapon(Weapon):

    def fire(self, camera):
        super().fire(camera)

        self.trace_shot(camera)

    @requires_netmode(Netmodes.server)
    def trace_shot(self, camera):
        hit_object, hit_position, hit_normal = camera.trace_ray(self.maximum_range)
        if not hit_object:
            return

        replicable = Actor.from_object(hit_object)

        if replicable == self.owner.pawn or not isinstance(replicable, Pawn):
            return

        hit_vector = (hit_position - camera.position)
        falloff = square_falloff(camera.position, self.maximum_range, hit_position, self.effective_range)
        damage = self.base_damage * falloff
        momentum = self.momentum * hit_vector.normalized() * falloff

        ActorDamagedSignal.invoke(damage, self.owner, hit_position, momentum, target=replicable)


class ProjectileWeapon(Weapon):

    def on_initialised(self):
        super().on_initialised()

        self.projectile_class = None
        self.projectile_velocity = Vector()

    def fire(self, camera):
        super().fire(camera)

        self.projectile_shot(camera)

    @requires_netmode(Netmodes.server)
    def projectile_shot(self, camera):
        projectile = self.projectile_class()
        forward_vector = Vector((0, 1, 0))
        forward_vector.rotate(camera.rotation)
        projectile.position = camera.position + forward_vector * 6.0
        projectile.rotation = camera.rotation.copy()
        projectile.velocity = self.projectile_velocity
        projectile.possessed_by(self)


class EmptyWeapon(Weapon):

    ammo = Attribute(0)
