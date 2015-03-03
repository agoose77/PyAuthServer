from copy import copy

from ..coordinates import Vector

__all__ = 'EPICExtrapolator', 'PhysicsExtrapolator'


class EPICExtrapolator:

    MINIMUM_DT = 0.01
    VALUE_TYPE = None

    def __init__(self):
        self._update_time = 0.0

        self._last_timestamp = 0.0
        self._snap_timestamp = 0.0
        self._target_timestamp = 0.0

        self._snap_value = self.VALUE_TYPE()
        self._target_value = self.VALUE_TYPE()
        self._last_value = self.VALUE_TYPE()

        self._snap_derivative = self.VALUE_TYPE()

    def add_sample(self, timestamp, current_time, new_value, new_derivative=None, c=1):
        """Add new sample to the extrapolator

        :param timestamp: timestamp of new sample
        :param current_time: timestamp sample was received
        :param current_value: position at current time
        :param new_value: position of new sample
        :param new_derivative: velocity of new sample
        """
        if new_derivative is None:
            new_derivative = self.determine_derivative(timestamp, new_value)

        if timestamp <= self._last_timestamp:
            return

        new_value = copy(new_value)
        new_derivative = copy(new_derivative)

        self.update_estimates(timestamp)

        self._last_value = new_value
        self._last_timestamp = timestamp

        self._snap_value = self.sample_at(current_time)[0]
        self._snap_timestamp = current_time

        self._target_timestamp = current_time + self._update_time

        delta_time = self._target_timestamp - timestamp
        self._target_value = new_value + new_derivative * delta_time

        if abs(self._target_timestamp - self._snap_timestamp) < self.__class__.MINIMUM_DT:
            self._snap_derivative = new_derivative

        else:
            inv_delta_time = 1.0 / (self._target_timestamp - self._snap_timestamp)
            self._snap_derivative = (self._target_value - self._snap_value) * inv_delta_time

    def determine_derivative(self, timestamp, value):
        """Determine velocity required to move to a given position with respect to the delta time

        :param timestamp: timestamp of new position
        :param value: target position
        """
        if abs(timestamp - self._last_timestamp) > self.__class__.MINIMUM_DT:
            inv_delta_time = 1.0 / (timestamp - self._last_timestamp)
            derivative = (value - self._last_value) * inv_delta_time

        else:
            derivative = self.VALUE_TYPE()

        return derivative

    def sample_at(self, request_time):
        """Sample the extrapolator for timestamp

        :param request_time: timestamp of sample
        """
        max_timestamp = self._target_timestamp

        valid = True
        if request_time < self._snap_timestamp:
            request_time = self._snap_timestamp
            valid = False

        if request_time > max_timestamp:
            request_time = max_timestamp
            valid = False

        derivative = self._snap_derivative.copy()
        value = self._snap_value + derivative * (request_time - self._snap_timestamp)

        if not valid:
            derivative = self.VALUE_TYPE()

        return value, derivative

    def reset(self, timestamp, current_time, value, derivative):
        """Ignore previous samples and base extrapolator upon new data

        :param timestamp: timestamp of base sample
        :param current_time: current timestamp
        :param value: position of base sample
        :param derivative: velocity of base sample
        """
        assert timestamp <= current_time
        self._last_timestamp = timestamp
        self._last_value = value
        self._snap_timestamp = current_time
        self._snap_value = value
        self._update_time = current_time - timestamp
        self._target_timestamp = current_time + self._update_time
        self._snap_derivative = derivative
        self._target_value = value + derivative * self._update_time

    def update_estimates(self, timestamp):
        """Update extrapolator estimate of the update time

        :param timestamp: timestamp of new sample
        """
        update_time = timestamp - self._last_timestamp
        if update_time > self._update_time:
            self._update_time = (self._update_time + update_time) * 0.5

        else:
            n = 8
            self._update_time = (self._update_time * (n - 1) + update_time) * (1 / n)


class PhysicsExtrapolator(EPICExtrapolator):

    VALUE_TYPE = Vector