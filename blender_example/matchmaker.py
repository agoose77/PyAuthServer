from json import loads
from urllib import request, parse
from functools import partial
from queue import Empty as EmptyQueue

from bge_network.signals import GameExitSignal
from bge_network.threads import SafeThread
from network.signals import SignalListener, UpdateSignal


class URLThread(SafeThread):
    """Thread responsible for handling URL requests"""

    def handle_task(self, task, queue):
        callback, data, url = task
        request_obj = request.Request(url, data=data)
        response_obj = request.urlopen(request_obj)
        response_data = response_obj.read().decode()
        queue.put((callback, response_data))


def json_decoder(callback, data):
    """Decodes JSON data into Python types

    :param callback: callback to handle processed data
    :param data: JSON encoded data
    """
    try:
        data = loads(data)

    except ValueError:
        data = None

    if callable(callback):
        return callback(data)


class Matchmaker(SignalListener):
    """Handles state information and connection requests for hosted servers"""

    def __init__(self, url):
        self.register_signals()

        self.url = url
        self.thread = URLThread()
        self.thread.start()

    def perform_query(self, callback=None, data=None, is_json=True):
        if data is not None:
            data_bytes = [(a.encode(), str(b).encode()) for (a, b) in data]
            parsed_data = parse.urlencode(data_bytes).encode()

        else:
            parsed_data = None

        # Use JSON decoder
        if is_json:
            callback = partial(json_decoder, callback)

        self.thread.in_queue.put((callback, parsed_data, self.url))

    @staticmethod
    def server_query():
        return None

    @staticmethod
    def register_query(name, map_name, max_players, players):
        """Builds register query for URL request

        :param name: name of server to be registered
        :param max_players: maximum number of players supported
        :param players: initial number of connected players
        """
        data = [("is_server", True), ("max_players", max_players), ("map", map_name), ("name", name),
                ("players", players)]

        return data

    @staticmethod
    def poll_query(server_id, name, map_name, max_players, players):
        """Builds update query for URL request

        :param server_id: ID delegated by matchmaking server to represent server
        :param name: name of server represented by this matchmaker
        :param max_players: maximum number of players supported
        :param map_name: name of current map being played
        :param players: initial number of connected players
        """
        data = [("is_server", True), ("max_players", max_players), ("map", map_name), ("name", name),
                ("players", players), ("update_id", server_id)]

        return data

    @staticmethod
    def unregister_query(server_id):
        """Builds unregister query for URL request

        :param server_id: ID delegated by matchmaking server to represent server
        """
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
    """Matchmaker which is bound to a server instance"""

    def __init__(self, url):
        super().__init__(url)

        self._id = None
        self._name = None

    def register(self, name, *args, **kwargs):
        """Register server with matchmaking server

        :param name: name of server to register
        :param *args: additional arguments for register query
        :param **kwargs: additional keyword arguments for register query
        """
        id_setter = partial(self.__setattr__, "_id")
        register_query = self.register_query(name, *args, **kwargs)
        self.perform_query(id_setter, register_query)

        self._name = name

    def poll(self, *args, **kwargs):
        """Update server information with matchmaking server

        :param *args: additional arguments for poll query
        :param **kwargs: additional keyword arguments for poll query
        """
        if self._name is None:
            raise ValueError("Matchmaker must first be registered before polling status")

        poll_query = self.poll_query(self._id, self._name, *args, **kwargs)
        self.perform_query(data=poll_query)

    def unregister(self):
        """Unregister server from matchmaking server"""
        unregister_query = self.unregister_query(self._id)
        self.perform_query(data=unregister_query)

    @UpdateSignal.global_listener
    def update(self, delta_time):
        super().update()

    @GameExitSignal.global_listener
    def on_quit(self):
        self.unregister()

        super().on_quit()
