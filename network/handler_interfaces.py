from .serialiser import UInt8, UInt16, UInt32, UInt64, Float8, Float4, String
from bitarray import bits2bytes

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
    
def int_footprint(value):
    '''Returns the size of the number in bytes'''
    return bits2bytes(value.bit_length())

def smallest_int_handler(value, bits=False):
    '''Handles integer sizes specifically'''
    if bits:
        bytes_ = bits2bytes(value)
    else:
        bytes_ = int_footprint(value)
        
    for index, char in enumerate((UInt8, UInt16, UInt32, UInt64)):
        size = 2 ** index
        if size >= bytes_:
            return char
        
def get_handler(value):
    '''Takes a StaticValue (or subclass thereof) and return handler
    @param value: StaticValue subclass'''
    if value._type is str:
        return String
    
    elif value._type is int:
        return smallest_int_handler(value._kwargs.get("max_value", 8))
    
    elif value._type is float:
        return Float8 if value._kwargs.get("max_precision") else Float4
    
    try:    
        callback, is_condition = handlers[value._type]
    except KeyError:
        raise TypeError("No handler for object with type {}".format(value._type))
    else:
        return callback(value) if is_condition else callback
