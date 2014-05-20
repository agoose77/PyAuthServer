
__all__ = ['IPhysicsObject', 'IAnimatedObject']


class IAnimatedObject:

    def get_animation_frame(self, layer):
        raise NotImplementedError()

    def play_animation(self, name, start, end, layer, priority, blend, mode, weight, speed, blend_mode):
        raise NotImplementedError()

    def stop_animation(self, layer):
        raise NotImplementedError()


class IPhysicsObject:

    @property
    def angular(self):
        raise NotImplementedError()

    @angular.setter
    def angular(self, angular):
        raise NotImplementedError()

    @property
    def collision_group(self):
        raise NotImplementedError()

    @collision_group.setter
    def collision_group(self, collision_group):
        raise NotImplementedError()

    @property
    def collision_mask(self):
        raise NotImplementedError()

    @collision_mask.setter
    def collision_mask(self, collision_mask):
        raise NotImplementedError()

    @property
    def lifespan(self):
        raise NotImplementedError()

    @lifespan.setter
    def lifespan(self, lifespan):
        raise NotImplementedError()

    @property
    def local_angular(self):
        raise NotImplementedError()

    @local_angular.setter
    def local_angular(self, local_angular):
        raise NotImplementedError()

    @property
    def local_position(self):
        raise NotImplementedError()

    @local_position.setter
    def local_position(self, local_position):
        raise NotImplementedError()

    @property
    def local_rotation(self):
        raise NotImplementedError()

    @local_rotation.setter
    def local_rotation(self, local_rotation):
        raise NotImplementedError()

    @property
    def local_velocity(self):
        raise NotImplementedError()

    @local_velocity.setter
    def local_velocity(self, local_velocity):
        raise NotImplementedError()

    @property
    def parent(self):
        raise NotImplementedError()

    @property
    def position(self):
        raise NotImplementedError()

    @position.setter
    def position(self, position):
        raise NotImplementedError()

    @property
    def rotation(self):
        raise NotImplementedError()

    @rotation.setter
    def rotation(self, rotation):
        raise NotImplementedError()

    @property
    def transform(self):
        raise NotImplementedError()

    @transform.setter
    def transform(self, transform):
        raise NotImplementedError()

    @property
    def velocity(self):
        raise NotImplementedError()

    @velocity.setter
    def velocity(self, velocity):
        raise NotImplementedError()

    def add_child(self, child):
        raise NotImplementedError()

    def get_direction(self, axis):
        raise NotImplementedError()

    def remove_child(self, child):
        raise NotImplementedError()

    def set_parent(self, parent, socket_name):
        raise NotImplemented()

    def trace_ray(self, target, source, distance):
        raise NotImplementedError()
