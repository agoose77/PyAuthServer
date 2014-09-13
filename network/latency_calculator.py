from collections import deque
from math import sqrt
from time import clock

from .maths_utilities import mean, median

__all__ = ['LatencyCalculator']


class LatencyCalculator:

    def __init__(self, sample_count=6):
        self._pending_samples = {}
        self._samples = deque(maxlen=sample_count)
        self._sample_count = sample_count

        self.round_trip_time = 0.0

    def _calculate_latency(self):
        samples = self._samples

        mean_value = mean(samples)
        median_value = median(samples)

        sum_of_squares = sum((x - mean_value) ** 2 for x in samples)
        variance = sum_of_squares / (len(samples) - 1)
        standard_deviation = sqrt(variance)

        self.round_trip_time = mean((x for x in samples if abs(x - median_value) <= standard_deviation))

    def start_sample(self, sample_id):
        """Start timing latency for sample

        :param sample_id: ID of sample
        """
        start_time = clock()
        self._pending_samples[sample_id] = start_time

    def stop_sample(self, sample_id):
        """Stop timing latency for sample.
        After enough samples are gathered, the latency is computed

        :param sample_id: ID of sample
        """
        end_time = clock()
        start_time = self._pending_samples[sample_id]

        round_trip = end_time - start_time
        self._samples.append(round_trip)

        if len(self._samples) == self._sample_count:
            self._calculate_latency()