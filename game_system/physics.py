from .coordinates import Vector
from. definitions import EnvironmentDefinitionByTag


__all__ = ["PhysicsSystem", "EPICExtrapolator"]


# HANDLE NETMODE DELEGATION AND ENV DELEGATION
class PhysicsSystem(EnvironmentDefinitionByTag):
    subclasses = {}


class EPICExtrapolator:

    MINIMUM_DT = 0.01

    def __init__(self):
        self._update_time = 0.0
        self._last_timestamp = 0.0
        self._snap_timestamp = 0.0
        self._target_timestamp = 0.0

        self._snap_position = Vector()
        self._target_position = Vector()
        self._snap_velocity = Vector()
        self._last_position = Vector()

    def add_sample(self, timestamp, current_time, current_position, position, velocity=None):
        """Add new sample to the extrapolator

        :param timestamp: timestamp of new sample
        :param current_time: timestamp sample was received
        :param current_position: position at current time
        :param position: position of new sample
        :param velocity: velocity of new sample
        """
        if velocity is None:
            velocity = self.determine_mean_velocity(timestamp, position)

        if timestamp <= self._last_timestamp:
            return

        position = position.copy()
        velocity = velocity.copy()

        self.update_estimates(timestamp)

        self._last_position = position
        self._last_timestamp = timestamp

        self._snap_position = current_position.copy()
        self._snap_timestamp = current_time

        self._target_timestamp = current_time + self._update_time

        delta_time = self._target_timestamp - timestamp
        self._target_position = position + velocity * delta_time

        if abs(self._target_timestamp - self._snap_timestamp) < self.__class__.MINIMUM_DT:
            self._snap_velocity = velocity

        else:
            delta_time = 1.0 / (self._target_timestamp - self._snap_timestamp)
            self._snap_velocity = (self._target_position - self._snap_position) * delta_time

    def determine_mean_velocity(self, timestamp, position):
        """Determine velocity required to move to a given position with respect to the delta time

        :param timestamp: timestamp of new position
        :param position: target position
        """
        if abs(timestamp - self._last_timestamp) > self.__class__.MINIMUM_DT:
            delta_time = 1.0 / (timestamp - self._last_timestamp)
            velocity = (position - self._last_position) * delta_time

        else:
            velocity = Vector()

        return velocity

    def sample_at(self, request_time):
        """Sample the extrapolator for timestamp

        :param request_time: timestamp of sample
        """
        max_timestamp = self._target_timestamp + self._update_time

        valid = True
        if request_time < self._snap_timestamp:
            request_time = self._snap_timestamp
            valid = False

        if request_time > max_timestamp:
            request_time = max_timestamp
            valid = False

        velocity = self._snap_velocity.copy()
        position = self._snap_position + velocity * (request_time - self._snap_timestamp)

        if not valid:
            velocity.zero()

        return position, velocity

    def reset(self, timestamp, current_time, position, velocity):
        """Ignore previous samples and base extrapolator upon new data

        :param timestamp: timestamp of base sample
        :param current_time: current timestamp
        :param position: position of base sample
        :param velocity: velocity of base sample
        """
        assert timestamp <= current_time
        self._last_timestamp = timestamp
        self._last_position = position
        self._snap_timestamp = current_time
        self._snap_position = position
        self._update_time = current_time - timestamp
        self._target_timestamp = current_time + self._update_time
        self._snap_velocity = velocity
        self._target_position = position + velocity * self._update_time

    def update_estimates(self, timestamp):
        """Update extrapolator estimate of the update time

        :param timestamp: timestamp of new sample
        """
        update_time = timestamp - self._last_timestamp
        if update_time > self._update_time:
            self._update_time = (self._update_time + update_time) * 0.5

        else:
            self._update_time = (self._update_time * 7 + update_time) * 0.125