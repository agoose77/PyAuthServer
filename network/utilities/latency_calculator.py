from collections import deque
from math import sqrt
from time import clock

from . import mean, median


class LatencyCalculator:
    """Estimate round-trip latency of connection"""

    def __init__(self, sample_count=8):
        self._pending_samples = {}
        self._samples = deque(maxlen=sample_count)
        self._sample_count = sample_count
        self._sample_id = 0

        self.round_trip_time = 0.0
        self.on_updated = None

    def _calculate_latency(self):
        samples = self._samples

        mean_value = mean(samples)
        median_value = median(samples)

        sum_of_squares = sum((x - mean_value) ** 2 for x in samples)
        variance = sum_of_squares / (len(samples) - 1)
        standard_deviation = sqrt(variance)

        self.round_trip_time = mean((x for x in samples if abs(x - median_value) <= standard_deviation))

        if callable(self.on_updated):
            self.on_updated(self.round_trip_time)

    def start_sample(self):
        """Start timing latency for sample

        :param sample_id: ID of sample
        """
        sample_id = self._sample_id
        self._pending_samples[sample_id] = clock()

        self._sample_id += 1
        return sample_id

    def stop_sample(self, sample_id):
        """Stop timing latency for sample.
        After enough samples are gathered, the latency is computed

        :param sample_id: ID of sample
        """
        try:
            started_time = self._pending_samples.pop(sample_id)

        except KeyError:
            return

        self._samples.append(clock() - started_time)
        if len(self._samples) == self._sample_count:
            self._calculate_latency()

    def ignore_sample(self, sample_id):
        """Stop timing latency for sample.

        :param sample_id: ID of sample
        """
        try:
            del self._pending_samples[sample_id]

        except KeyError:
            return
