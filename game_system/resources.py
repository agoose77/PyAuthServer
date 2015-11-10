from json import loads
from os import path

from .configobj import ConfigObj


class ResourceManager:

    def __init__(self, root_path):
        self.root_path = root_path

    def open_file(self, file_name, mode='r'):
        return open(path.join(self.root_path, file_name), mode)

    def open_json(self, file_name, mode='r'):
        with self.open_file(file_name, mode) as f:
            return loads(f.read())

    def open_configuration(self, file_name, defaults=None, interpolation='template'):
        with self.open_file(file_name) as f:
            parser = ConfigObj(f, interpolation=interpolation)

        parser['DEFAULT'] = defaults
        return parser