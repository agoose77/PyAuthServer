from game_system import IResourceManager

from os import path, walk

__all__ = ["BGEResourceManager", "ResourceManager"]


class BGEResourceManager(IResourceManager):

    def from_relative_path(self, relative_path):
        return path.join(self.data_path, relative_path)

    def load_resource(self, name):
        resource_folder = path.join(self.data_path, name)
        try:
            _, *resource_groups = list(walk(resource_folder))

        except ValueError as err:
            raise LookupError("{} could not be found in data path"
                              .format(name)) from err

        resources = {}
        for file_path, _, files in resource_groups:
            resource_type = path.basename(file_path)
            resource_map = {f: path.join(file_path, f) for f in files}
            resources[resource_type] = resource_map

        return resources


ResourceManager = BGEResourceManager()
