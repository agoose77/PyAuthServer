from game_system.coordinates import Vector
from game_system.entities import Actor
from game_system.enums import Axis, SpatialEventType
from game_system.signals import HearSoundSignal

from network.signals import SignalListener

from math import radians, tan
from operator import attrgetter


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


class SpatialEvent:

    def __init__(self, event_type, position, distance, data, lifespan=1):
        self.type = event_type
        self.position = position
        self.distance = distance
        self.data = data
        self.lifespan = lifespan
        self.age = 0.0

    @property
    def expired(self):
        return self.age > self.lifespan

    @property
    def is_new(self):
        return not self.age

    def __repr__(self):
        return "<SpatialEvent ({}) @ {}> : {}".format(SpatialEventType[self.type], self.distance, self.data)


class SoundSensor(Sensor, SignalListener):

    def __init__(self):
        super().__init__()

        self.origin = Vector()
        self.distance = 50

        self._heard_sounds = []

    @HearSoundSignal.on_global
    def hear_sound(self, sound):
        intensity = sound.bounds.get_linear_intensity(self.origin, self.distance)

        if not intensity:
            return

        self._heard_sounds.append(sound)

    def update(self, dt):
        self._heard_sounds.clear()


class ViewSensor(Sensor):

    def __init__(self):
        super().__init__()

        self.view_cone = ViewCone(radians(30), 50)

        self._seen_actors_to_events = {}

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

        seen_event = SpatialEventType.sight
        seen_events = self._seen_actors_to_events
        facts = self.controller.fact_manager.facts

        not_updated_actors = set(seen_events)

        for actor in Actor.subclass_of_type(Actor):
            actor_position = actor.transform.world_position
            if actor_position not in view_cone:
                continue

            result = actor.physics.ray_test(actor_position, pawn_position)
            if result is None:
                continue

            if result.entity is not actor:
                continue

            distance = (actor_position - pawn_position).length

            # Recall continuous events
            try:
                event = seen_events[actor]
                event.position = actor_position
                event.distance = distance
                event.age = 0.0

                # Remove event
                not_updated_actors.remove(actor)

            except KeyError:
                event = SpatialEvent(seen_event, actor_position, distance, actor)

                # Add fact
                facts.append(event)
                seen_events[actor] = event

        # Check for expired events
        for actor in not_updated_actors:
            event = seen_events[actor]

            if event.expired:
                del seen_events[actor]


class SpatialFactManager:

    def __init__(self):
        self.facts = []
        self._key_func = attrgetter("distance")

    def update(self):
        self.facts[:] = [f for f in self.facts if not f.expired]
        self.facts.sort(key=self._key_func)