from json import loads
from urllib import request, parse


class Matchmaker:

    def __init__(self, url):
        self.url = url

    def json_query(self, data=None, decode_reply=True):

        if data is not None:
            bytes_data = [(a.encode(), str(b).encode()) for (a, b) in data]
            parsed_data = parse.urlencode(bytes_data).encode()
        else:
            parsed_data = None

        request_obj = request.Request(self.url, data=parsed_data)
        response_obj = request.urlopen(request_obj)
        response_data = response_obj.read().decode()

        if decode_reply:
            try:
                return loads(response_data)
            except ValueError:
                if response_data:
                    raise
                return None

    def read_servers(self):
        return self.json_query()

    def register_server(self, name, map_name, max_players, players):
        data = [("is_server", True), ("max_players", max_players),
                ("map", map_name), ("name", name), ("players", players)]

        return self.json_query(data)

    def update_server(self, server_id, name, map_name, max_players, players):
        data = [("is_server", True), ("max_players", max_players),
                ("map", map_name), ("name", name), ("players", players),
                ("update_id", server_id)]

        return self.json_query(data)

    def unregister_server(self, server_id):
        data = [("is_server", True), ("delete_id", server_id)]

        return self.json_query(data)


class BoundMatchmaker(Matchmaker):

    def __init__(self, url):
        super().__init__(url)

        self._id = None

    def register_server(self, name, *args, **kwargs):
        self._id = super().register_server(name, *args, **kwargs)
        self._name = name

    def update_server(self, *args, **kwargs):
        super().update_server(self._id, self._name, *args, **kwargs)

    def unregister_server(self):
        super().unregister_server(self._id)
