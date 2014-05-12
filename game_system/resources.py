

__all__ = ["IResourceManager"]


class IResourceManager:

    def __init__(self):
        self._data_path = None

    @property
    def data_path(self):
        return self._data_path

    @data_path.setter
    def data_path(self, path):
        self._data_path = path

    def from_relative_path(self, relative_path):
        raise NotImplementedError()

    def load_resource(self, name):
        raise NotImplementedError()

