handlers = {}
descriptions = {}

def static_description(obj):
    '''Uses hash-like comparison of muteable and/or immuteable data
    @param obj: object to describe'''
    if hasattr(obj, "__description__"):
        return obj.__description__()
    
    elif type(obj) in descriptions:
        return descriptions[type(obj)](obj)
    
    return hash(obj)

def register_handler(type_, callable_, is_condition=False):
    '''Registers new handler for custom serialisers
    @param type_: type of object
    @param callable: callable to run
    @param is_condition: whether callable is generic or requires object'''
    handlers[type_] = callable_, is_condition

def register_description(type_, callable):
    '''Registers special description for non-subclassable types
    @param type_: type of object
    @param callable: callable for description'''
    descriptions[type_] = callable
        
def get_handler(value):
    '''Takes a StaticValue (or subclass thereof) and return handler
    @param value: StaticValue subclass'''
    
    value_type = value.type
    
    if not value_type in handlers:
        
        handled_superclasses = [cls for cls in value.type.__mro__ if cls in handlers]
        
        try:
            value_type = handled_superclasses[0]
        except IndexError:
            raise TypeError("No handler for object with type {}".format(value.type))
    
    callback, is_condition = handlers[value_type]
    
    return callback(value) if is_condition else callback
