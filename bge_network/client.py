from bge import logic, events; import sys; sys.path.append(logic.expandPath("//../"))

from network import WorldInfo, BaseRules, Connection, Netmodes, Roles

from errors import *
from actors import *
from enums import *

from game import Game
from random import randint

import attributes

# Setup game
WorldInfo.netmode = Netmodes.client

class ClientGame(Game):
    
    def __init__(self, addr="127.0.0.1", port=0, server=("127.0.0.1", 1200)):
        super().__init__(addr, port)
        
        self.conn = self.connect_to(server)
    
game = ClientGame() 

def main(cont):
    
    try:
        controller = next(WorldInfo.subclass_of(PlayerController))
    except StopIteration:
        pass
    else:
        if not controller.name:
            controller.set_name("FakeName")
    
    try:
        game.update() 
    except QuitGame:
        logic.endGame()    