from .entities import Actor


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


class ViewSensor(Sensor):

    def sample(self):
        distances = {}

        controller = self.controller
        pawn = controller.pawn

        if pawn is None:
            return

        pawn_position = pawn.transform.world_position
        for actor in Actor.subclass_of_type(Actor):
            distances[actor] = (actor.transform.world_position - pawn_position).length