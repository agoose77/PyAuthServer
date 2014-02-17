__all__ = ['FactoryDict']


def FactoryDict(factory_func, dict_type=dict, provide_key=True):
    def missing_key(self, key):
        value = self[key] = factory_func(key)
        return value

    def missing(self, key):
        value = self[key] = factory_func()
        return value

    callback = missing_key if provide_key else missing

    return type("FactoryDict", (dict_type,), {"__missing__": callback})()
