__all__ = ["BidirectionalIterator"]


class BidirectionalIterator:
    def __init__(self, collection):
        self.collection = collection
        self.index = -1

    def __next__(self):
        try:
            self.index += 1
            result = self.collection[self.index]
        except IndexError:
            raise StopIteration
        return result

    def __prev__(self):
        self.index -= 1
        if self.index < 0:
            raise StopIteration
        return self.collection[self.index]

    def __iter__(self):
        return self
