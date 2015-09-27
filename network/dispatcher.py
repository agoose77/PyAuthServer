class UniqueMessageDispatcher:

    def __init__(self):
        self._listeners = {}

    def send(self, identifier, message):
        try:
            listener = self._listeners[identifier]
            
        except KeyError:
            raise ValueError("Invalid identifier '{}' given, have {}".format(identifier, self._listeners))
        
        listener(message)

    def set_listener(self, identifier, listener):
        if identifier in self._listeners:
            raise ValueError("'{}' already in listeners".format(identifier))
        
        self._listeners[identifier] = listener