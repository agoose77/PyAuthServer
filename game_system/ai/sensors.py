from math import radians, tan

from ..coordinates import Vector
from ..entity import Actor
from ..enums import Axis


class Sound:

    def __init__(self, path, bounds):
        self.path = path
        self.bounds = bounds


class SphericalBounds:

    def __init__(self, origin, radius):
        self.origin = origin
        self.radius = radius
        self.radius_sq = radius ** 2

    def get_linear_intensity(self, point, falloff_rate):
        offset = (point - self.origin).length
        if offset > self.radius:
            return 0.0

        return 1 - (offset / falloff_rate)

    def get_quadratic_intensity(self, point, falloff_rate):
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
        # Update sensors
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
        width = (to_point - depth * self.direction).length

        return width < radius_at_depth


class SightInterpreter:

    def handle_visible_actors(self, actors):
        pass


class SoundSensor(Sensor):

    def __init__(self):
        super().__init__()

        self.distance = 50

        self._pending_links = []

    def hear_sound(self, sound):
        pawn = self.controller.pawn
        if pawn is None:
            return

        pawn_position = pawn.transform.world_position

        intensity = sound.bounds.get_linear_intensity(pawn_position, self.distance)
        if not intensity:
            return

        distance = (sound.bounds.origin - pawn_position).length

        fact = SensoryLink(sound.bounds.origin, distance, sound)
        self._pending_links.append(fact)

    def update(self, dt):
        self.links.extend(self._pending_links)
        self._pending_links.clear()


class SightSensor(Sensor):

    def __init__(self):
        super().__init__()

        self.view_cone = ViewCone(radians(67.5), 50)
        self.sample_frequency = 8
        self._interpreters = set()

    def add_interpreter(self, interpreter):
        interpreter.sensor = self
        self._interpreters.add(interpreter)

    def remove_interpreter(self, interpreter):
        interpreter.sensor = None
        self._interpreters.remove(interpreter)

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
        ray_test = pawn.physics.ray_test
        for actor in Actor.subclass_of_type(Actor):
            # actor_position = actor.transform.world_position
            #
            # if actor_position not in view_cone:
            #     continue
            #
            # result = ray_test(actor_position)
            # if result is None:
            #     continue

            visible_actors.append(actor)

        for interpreter in self._interpreters:
            interpreter.handle_visible_actors(visible_actors)
