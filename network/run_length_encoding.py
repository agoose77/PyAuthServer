from itertools import groupby

__all__ = ["RunLengthCodec"]


class RunLengthCodec:
    """RLE compression codec"""

    @staticmethod
    def encode(sequence):
        """Apply run length encoding to a sequence

        Returns a list of (count, item) pairs
        :param sequence: sequence of values to encode
        """
        return [(len(list(group)), key) for key, group in groupby(sequence)]

    @staticmethod
    def decode(sequence):
        """Parse run length encoding from a sequence

        Returns original sequence as a list
        :param sequence: sequence of value pairs to decode
        """
        return [key for (length, key) in sequence for _ in range(length)]