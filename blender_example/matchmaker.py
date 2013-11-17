from json import loads
from urllib import request, parse
from functools import partial

from threads import QueuedThread
from bge_network import GameExitSignal, SignalListener

import queue


class URLThread(QueuedThread):

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

    @GameExitSignal.global_listener
    def delete_thread(self):
        self.thread.join()

    def perform_query(self, callback=None, data=None, is_json=True):

        if data is not None:
            bytes_data = [(a.encode(), str(b).encode()) for (a, b) in data]
            parsed_data = parse.urlencode(bytes_data).encode()
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

            except queue.Empty:
                break
            if callable(callback):
                callback(response)


class BoundMatchmaker(Matchmaker):

    def __init__(self, url):
        super().__init__(url)

        self._id = None

    def register(self, name, *args, **kwargs):
        data = super().register_query(name, *args, **kwargs)
        callback = partial(self.__setattr__, "_id")
        self.perform_query(callback, data)
        self._name = name

    def poll(self, *args, **kwargs):
        data = super().poll_query(self._id, self._name, *args, **kwargs)
        self.perform_query(data=data)

    def unregister(self):
        data = super().unregister_query(self._id)
        self.perform_query(data=data)
