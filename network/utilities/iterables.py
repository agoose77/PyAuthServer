class LazyIterable:

    def __init__(self, get_iterable):
        self._get_iterable = get_iterable

    @property
    def _iterable(self):
        try:
            result = self._iterable_result

        except AttributeError:
            self._iterable_result = result = self._get_iterable()

        return result

    def __iter__(self):
        return iter(self._iterable)

    def __len__(self):
        return len(self._iterable)

    def __getitem__(self, index):
        return self._iterable[index]