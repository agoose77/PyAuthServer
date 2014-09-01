from collections import Mapping
from functools import partial
from json import loads
from urllib import request, parse

from game_system.signals import GameExitSignal, LogicUpdateSignal
from game_system.threads import SafeThread

from network.signals import SignalListener


class URLThread(SafeThread):
    """Thread responsible for handling URL requests"""

    def handle_task(self):
        """Handles a URL request in a separate thread, returning the results to the output queue

        :param task: requested task
        :param queue: output queue for result
        """
        with self.slave.guarded_request() as task:
            if task is None:
                return

            callback, data, url = task
            request_obj = request.Request(url, data=data)
            response_obj = request.urlopen(request_obj)

            response_data = response_obj.read().decode()
            self.slave.commit((callback, response_data))


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
        """Send a request to the server message thread

        :param callback: callback function to handle server response
        :param data: paired key-value mapping of request parameters
        :param is_json: whether the response is valid JSON
        """
        if data is not None:
            # Handle dictionaries
            if isinstance(data, Mapping):
                data = tuple(data.items())

            # Convert data
            data_bytes = [(a.encode(), str(b).encode()) for (a, b) in data]
            parsed_data = parse.urlencode(data_bytes).encode()

        else:
            parsed_data = None

        # Use JSON decoder
        if is_json:
            callback = partial(json_decoder, callback)

        request = (callback, parsed_data, self.url)
        self.thread.client.commit(request)

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
            with self.thread.client.guarded_request() as request:
                if request is None:
                    break

                callback, response = request

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

    @LogicUpdateSignal.global_listener
    def update(self, delta_time):
        super().update()

    @GameExitSignal.global_listener
    def on_quit(self):
        self.unregister()
        super().on_quit()
