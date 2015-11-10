from collections import defaultdict


class MessagePasser:

    def __init__(self):
        self._subscribers = defaultdict(list)
        self._dispatchers = []

    def add_subscriber(self, message_id, callback):
        self._subscribers[message_id].append(callback)

    def clear_subscribers(self):
        self._subscribers.clear()

    def add_dispatcher(self, dispatcher):
        self._dispatchers.append(dispatcher)

    def remove_dispatcher(self, dispatcher):
        self._dispatchers.remove(dispatcher)

    def remove_subscriber(self, message_id, callback):
        self._subscribers[message_id].remove(callback)

    def send(self, identifier, *args, **kwargs):
        try:
            callbacks = self._subscribers[identifier][:]

        except KeyError:
            return

        for callbacks in callbacks:
            callbacks(*args, **kwargs)

        for dispatcher in self._dispatchers[:]:
            dispatcher(identifier, *args, **kwargs)
