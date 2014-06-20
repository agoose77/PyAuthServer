__all__ = ['IPhysicsObjectMixin', 'IAnimatedObjectMixin', 'ITransformObjectMixin']


class IAnimatedObjectMixin:

    def get_animation_frame(self, layer):
        raise NotImplementedError()

    def play_animation(self, name, start, end, layer, priority, blend, mode, weight, speed, blend_mode):
        raise NotImplementedError()

    def stop_animation(self, layer):
        raise NotImplementedError()


class ITransformObjectMixin:

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
    def parent(self):
        raise NotImplementedError()

    @property
    def world_position(self):
        raise NotImplementedError()

    @world_position.setter
    def world_position(self, position):
        raise NotImplementedError()

    @property
    def world_rotation(self):
        raise NotImplementedError()

    @world_rotation.setter
    def world_rotation(self, rotation):
        raise NotImplementedError()

    @property
    def transform(self):
        raise NotImplementedError()

    @transform.setter
    def transform(self, transform):
        raise NotImplementedError()

    def add_child(self, child):
        raise NotImplementedError()

    def get_direction(self, axis):
        raise NotImplementedError()

    def remove_child(self, child):
        raise NotImplementedError()

    def set_parent(self, parent, socket_name):
        raise NotImplemented()


class IPhysicsObjectMixin:

    @property
    def world_angular(self):
        raise NotImplementedError()

    @world_angular.setter
    def world_angular(self, angular):
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
    def local_angular(self):
        raise NotImplementedError()

    @local_angular.setter
    def local_angular(self, local_angular):
        raise NotImplementedError()

    @property
    def local_velocity(self):
        raise NotImplementedError()

    @local_velocity.setter
    def local_velocity(self, local_velocity):
        raise NotImplementedError()

    @property
    def world_velocity(self):
        raise NotImplementedError()

    @world_velocity.setter
    def world_velocity(self, velocity):
        raise NotImplementedError()

    def trace_ray(self, target, source, distance):
        raise NotImplementedError()


class ICameraObjectMixin(IPhysicsObjectMixin):

    @property
    def active(self):
        raise NotImplementedError()

    @active.setter
    def active(self, status):
        raise NotImplementedError()

    @property
    def lens(self):
        raise NotImplementedError()

    @lens.setter
    def lens(self, value):
        raise NotImplementedError()

    @property
    def fov(self):
        raise NotImplementedError()

    @fov.setter
    def fov(self, value):
        raise NotImplementedError()

    def is_point_in_frustum(self, point):
        raise NotImplementedError()

    def is_sphere_in_frustum(self, point, radius):
        raise NotImplementedError()

    def screen_trace_ray(self, distance, x, y):
        raise NotImplementedError()