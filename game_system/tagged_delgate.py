from .resources import ResourceManager
from network.tagged_delegate import DelegateByTag

__all__ = ['EnvironmentDefinitionByTag']


class EnvironmentDefinitionByTag(DelegateByTag):

    @staticmethod
    def get_current_tag():
        return ResourceManager.environment