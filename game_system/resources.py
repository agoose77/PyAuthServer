from os import path, listdir

__all__ = ["ResourceManager", "Resource", "_ResourceManager"]


class BoundPath(str):

    def __new__(cls, absolute_path, relative_path):
        str_ = super().__new__(cls, relative_path)
        str_.absolute = absolute_path

        return str_


class Resource:

    def __init__(self, parent, folder):
        self.parent = parent
        self.folder = folder

        self.relative_path = self._get_relative_path()

        self._absolute_path = None
        self._folders = None
        self._files = None

    def __getitem__(self, name):
        if name in self.folders:
            return Resource(self, name)

        elif name in self.files:
            return path.join(self.relative_path, name)

    def __repr__(self):
        return "Resource: {}".format(self.relative_path)

    def _get_relative_path(self):
        """Find base path relative to upper most parent"""
        parent_folders = []
        # Follow parent tree
        child = self
        while child:
            parent_folders.append(child.folder)
            child = child.parent

        parent_folders.reverse()
        return path.join(*parent_folders)

    @property
    def folders(self):
        if self._folders is None:
            absolute_path = self.absolute_path
            self._folders = [f for f in listdir(absolute_path) if path.isdir(path.join(absolute_path, f))]

        return self._folders

    @property
    def files(self):
        if self._files is None:
            absolute_path = self.absolute_path
            self._files = [f for f in listdir(absolute_path) if path.isfile(path.join(absolute_path, f))]

        return self._files

    @property
    def absolute_path(self):
        if self._absolute_path is None:
            self._absolute_path = path.join(self.root.data_path, self.relative_path)

        return self._absolute_path

    @property
    def root(self):
        child = parent = self
        while parent is not None:
            child, parent = parent, child.parent

        return child

    def refresh(self):
        """Refresh internal path and file information"""
        self._folders = None
        self._files = None
        self._absolute_path = None


class _ResourceManager(Resource):

    def __init__(self):
        self._data_path = ""

        self.environment = None

        super().__init__(parent=None, folder="")

    @property
    def data_path(self):
        return self._data_path

    @data_path.setter
    def data_path(self, path_):
        self._data_path = path_
        self.refresh()

    def from_relative_path(self, relative_path):
        return path.join(self.data_path, relative_path)


ResourceManager = _ResourceManager()