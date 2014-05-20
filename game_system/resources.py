

__all__ = ["IResourceManager"]


class IResource:

    def __getitem__(self, name):
        raise NotImplementedError()

    def _get_base_path(self):
        raise NotImplementedError()


class IResourceManager(IResource):

    @property
    def data_path(self):
        raise NotImplementedError()

    @data_path.setter
    def data_path(self, path):
        raise NotImplementedError()

    def from_relative_path(self, relative_path):
        raise NotImplementedError()
