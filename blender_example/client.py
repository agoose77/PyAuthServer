from bge_network import Game, QuitGame
from network import WorldInfo, Netmodes
from bge import logic
 
import actors

# Setup game
WorldInfo.netmode = Netmodes.client

class ClientGame(Game):
    
    def __init__(self, addr="127.0.0.1", port=0, server=("127.0.0.1", 1200)):
        super().__init__(addr, port)
        
        self.conn = self.connect_to(server)
    
game = ClientGame() 

def main(cont):
    
    try:
        game.update() 
    except QuitGame:
        logic.endGame()    