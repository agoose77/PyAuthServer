from json import loads, dumps
from network import System

pages = dict(find_game="games.php", host_game="host.php")

class UrlInterface:
    def __init__(self, url):
        self.url = url
    
    def json_request(self, page_url, data):
        return    

class TestInterface(UrlInterface):
    
    def json_request(self, url, data):
        if url == pages['find_game']:
            return {"localhost": dict(players="", map="Test Arena ", ping=0.0)}

class Matchmaker(System):
    def __init__(self, matchmaker_url):
        super().__init__()
        
        self.url_interface = TestInterface(matchmaker_url)
        
    def find_games(self, game_options={}):        
        game_information = self.url_interface.json_request(pages["find_game"], game_options)
        return game_information