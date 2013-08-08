from collections import defaultdict
        
class FactoryDict(defaultdict):
    '''Dictionary with factory for missing keys
    Provides key to factory function provided to initialiser'''
    def __missing__(self, key):
        self[key] = value = self.default_factory(key)
        return value