from game_system.coordinates import Vector
from game_system.entities import Actor
from game_system.enums import Axis

from math import radians, tan


class SphericalBounds:

    def __init__(self, origin, radius):
        self.origin = origin
        self.radius = radius
        self.radius_sq = radius ** 2

    def get_linear_falloff(self, point, falloff_rate):
        offset = (point - self.origin).length
        if offset > self.radius:
            return 0.0

        return 1 - (offset / falloff_rate)

    def get_quadratic_falloff(self, point, falloff_rate):
        offset_sq = (point - self.origin).length_squared
        if offset_sq > self.radius_sq:
            return 0.0

        return 1 - (offset_sq / falloff_rate)

    def test(self, point):
        to_point = point - self.origin
        return to_point.length_squared > self.radius_sq


class SensorManager:

    def __init__(self, controller):
        self._sensors = []
        self.controller = controller

    def add_sensor(self, sensor):
        """Register sensor with sensor manager

        :param sensor: sensor to add
        """
        sensor.controller = self.controller
        self._sensors.append(sensor)

    def remove_sensor(self, sensor):
        """Deregister sensor from sensor manager

        :param sensor: sensor to remove
        """
        self._sensors.remove(sensor)
        sensor.controller = None

    def update(self, dt):
        """Update all registered sensors

        :param dt: time since last call to update
        """
        for sensor in self._sensors:
            sensor.update(dt)


class Sensor:
    """Base class for AI world sensors"""

    def __init__(self):
        self.controller = None
        self.sample_frequency = 60

        self._accumulator = 0.0

    def sample(self):
        """Perform potentially expensive sample operation"""

    def update(self, dt):
        """Update internal sensor state, according to sample frequency

        :param dt: time since last call to update
        """
        self._accumulator += dt

        sample_step = 1 / self.sample_frequency
        if self._accumulator > sample_step:
            self._accumulator -= sample_step

            self.sample()


class ViewCone:

    def __init__(self, fov, length):
        self._depth_to_radius = 0.0
        self._fov = 0.0

        self.fov = fov
        self.length = length

        self.origin = Vector()
        self.direction = Vector((0, 1, 0))

    @property
    def fov(self):
        return self._fov

    @fov.setter
    def fov(self, fov):
        self._fov = fov
        self._depth_to_radius = tan(self._fov)

    def __contains__(self, point):
        to_point = point - self.origin
        depth = to_point.dot(self.direction)

        if depth > self.length:
            return False

        radius_at_depth = depth * self._depth_to_radius
        return (to_point - depth * self.direction).length > radius_at_depth


class ViewSensor(Sensor):

    def __init__(self):
        super().__init__()

        self.view_cone = ViewCone(radians(30), 50)

    def sample(self):
        controller = self.controller
        pawn = controller.pawn

        if pawn is None:
            return

        pawn_position = pawn.transform.world_position

        # Update view cone
        view_cone = self.view_cone
        view_cone.origin = pawn_position
        view_cone.direction = pawn.transform.get_direction_vector(Axis.y)

        visible_actors = []
        for actor in Actor.subclass_of_type(Actor):
            actor_position = actor.transform.world_position
            if actor_position not in view_cone:
                continue

            result = actor.physics.ray_test(actor_position, pawn_position)
            if result is None:
                continue

            if result.entity is not actor:
                continue

            visible_actors.append(actor)