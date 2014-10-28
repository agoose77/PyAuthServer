from .resources import ResourceManager
from network.tagged_delegate import DelegateByTag

__all__ = ['EnvironmentDefinitionByTag']


class EnvironmentDefinitionByTag(DelegateByTag):

    """Resolve instantiated class according to ResourceManager's environment"""

    @staticmethod
    def get_current_tag():
        """Return the value corresponding to one of this class's subclasses' tag"""
        return ResourceManager.environment