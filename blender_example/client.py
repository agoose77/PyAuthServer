from bge_network import Game, QuitGame
from network import WorldInfo, Netmodes
from bge import logic

from ui import UIManager
from matchmaker import Matchmaker

import actors

# Setup game
WorldInfo.netmode = Netmodes.client

class ClientGame(Game):
    
    def __init__(self, addr="127.0.0.1", port=0):
        super().__init__(addr, port)
    
# Game instance
game = ClientGame() 

# UI manager
ui = UIManager(game)

# Game matchmaker
matchmaker = Matchmaker("http://gameservers.com")

# Get a FindGameUI instance, and configure it
find_game_ui = ui.get_system("FindGameUI")
find_game_ui.set_connector(game.connect_to)
find_game_ui.set_matchmaker(matchmaker)

def main(cont):
    
    try:
        game.update() 
    except QuitGame:
        logic.endGame()    