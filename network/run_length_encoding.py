from itertools import groupby

__all__ = ["RunLengthCodec"]


class RunLengthCodec:
    """RLE compression codec"""

    @staticmethod
    def encode(values):
        return [(len(list(group)), key) for key, group in groupby(values)]

    @staticmethod
    def decode(values):
        return [key for (length, key) in values for _ in range(length)]