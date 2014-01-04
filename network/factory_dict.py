from collections import defaultdict

__all__ = ['FactoryDict']


class FactoryDict(defaultdict):
    '''Dictionary with factory for missing keys
    Provides key to factory function provided to initialiser'''
    def __missing__(self, key):
        value = self[key] = self.default_factory(key)
        return value
