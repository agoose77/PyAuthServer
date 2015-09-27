from network.annotations.decorators import requires_netmode
from network.descriptors import Attribute
from network.enums import Netmodes, Roles
from network.replicable import Replicable
from network.world_info import WorldInfo

from .enums import Axis
from .resources import ResourceManager
from .signals import *

from .coordinates import Vector


__all__ = ['Weapon', 'TraceWeapon', 'ProjectileWeapon']


class Weapon(Replicable):

    ammo = Attribute(70, notify=True)
    roles = Attribute(Roles(Roles.authority, Roles.autonomous_proxy))

    @property
    def can_fire(self):
        cool_down_ticks = self.shoot_interval * WorldInfo.tick_rate
        ticks_since_fired = (WorldInfo.tick - self.last_fired_tick)

        cool_down_expired = ticks_since_fired >= cool_down_ticks
        has_ammo = self.ammo != 0

        return has_ammo and cool_down_expired

    @property
    def resources(self):
        return ResourceManager[self.__class__.__name__]

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

        self.attachment_class = None
        self.base_damage = 40
        self.effective_range = 10
        self.last_fired_tick = 0
        self.maximum_range = 20
        self.momentum = 1
        self.max_ammo = 70
        self.shoot_interval = 0.5


class TraceWeapon(Weapon):

    def fire(self, camera):
        super().fire(camera)

        self.trace_shot(camera)

    @requires_netmode(Netmodes.server)
    def trace_shot(self, camera):
        # Get hit results
        camera_physics = camera.physics
        camera_transform = camera.transform
        camera_position = camera_transform.world_position
        position = camera_position + camera_physics.get_direction_vector(Axis.y)
        hit_result = camera_physics.ray_test(position, self.maximum_range)

        if not hit_result:
            return

        # But don't damage our owner!
        replicable = hit_result.entity

        if replicable is self.owner.pawn:
            return

        hit_position = hit_result.position
        hit_vector = (hit_position - camera_position)

        falloff = 1.0

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

        forward_vector = camera.physics.get_direction(Axis.y)
        projectile_vector = self.projectile_velocity.copy()
        projectile_vector.rotate(camera.transform.world_orientation)

        projectile.transform.world_position = camera.transform.world_position + forward_vector * 6.0
        projectile.transform.world_orientation = Vector((0, 1, 0)).rotation_difference(projectile_vector)
        projectile.physics.local_velocity = self.projectile_velocity
        projectile.physics.possessed_by(self)