from json import loads
from urllib import request, parse
from functools import partial
from queue import Empty as EmptyQueue

from bge_network.signals import GameExitSignal
from bge_network.threads import SafeThread
from network.signals import SignalListener, UpdateSignal


class URLThread(SafeThread):

    def handle_task(self, task, queue):
        callback, data, url = task
        request_obj = request.Request(url, data=data)
        response_obj = request.urlopen(request_obj)
        response_data = response_obj.read().decode()
        queue.put((callback, response_data))


def json_decoded(callback, data):
    try:
        data = loads(data)

    except ValueError:
        data = None

    if callable(callback):
        return callback(data)


class Matchmaker(SignalListener):

    def __init__(self, url):
        self.register_signals()

        self.url = url
        self.thread = URLThread()
        self.thread.start()

    def perform_query(self, callback=None, data=None, is_json=True):
        if data is not None:
            bytes_stringdata = [(a.encode(), str(b).encode()) for (a, b) in data]
            parsed_data = parse.urlencode(bytes_stringdata).encode()

        else:
            parsed_data = None

        if is_json:
            callback = partial(json_decoded, callback)

        self.thread.in_queue.put((callback, parsed_data, self.url))

    def server_query(self):
        return None

    def register_query(self, name, map_name, max_players, players):
        data = [("is_server", True), ("max_players", max_players),
                ("map", map_name), ("name", name), ("players", players)]

        return data

    def poll_query(self, server_id, name, map_name, max_players, players):
        data = [("is_server", True), ("max_players", max_players),
                ("map", map_name), ("name", name), ("players", players),
                ("update_id", server_id)]
        return data

    def unregister_query(self, server_id):
        data = [("is_server", True), ("delete_id", server_id)]

        return data

    def update(self):
        while True:
            try:
                (callback, response) = self.thread.out_queue.get_nowait()

            except EmptyQueue:
                break

            if callable(callback):
                callback(response)

    @GameExitSignal.global_listener
    def on_quit(self):
        del self.thread


class BoundMatchmaker(Matchmaker):

    def __init__(self, url):
        super().__init__(url)

        self._id = None

    def register(self, name, *args, **kwargs):
        data = self.register_query(name, *args, **kwargs)
        id_setter = partial(self.__setattr__, "_id")
        self.perform_query(id_setter, data)
        self._name = name

    def poll(self, *args, **kwargs):
        self.perform_query(data=self.poll_query(self._id,
                                                self._name,
                                                *args,
                                                **kwargs))

    def unregister(self):
        self.perform_query(data=self.unregister_query(self._id))

    @UpdateSignal.global_listener
    def update(self, delta_time):
        super().update()

    @GameExitSignal.global_listener
    def on_quit(self):
        self.unregister()

        super().on_quit()
