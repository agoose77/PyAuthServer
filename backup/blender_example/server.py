from bge import logic
from bge_network import Game, Actor, QuitGame

from rules import TeamDeathMatch
from network import WorldInfo, Netmodes

from random import randint

from actors import Player

# Add random actors
def random_spawn(n):
    '''Spawns randomly positioned actors'''
    for i in range(n):
        a = Player()
        a.physics.position[:] = randint(-10, 10), randint(-10, 10), 20

# Set network mode
WorldInfo.netmode = Netmodes.server
WorldInfo.rules = TeamDeathMatch

# Get game instance
game = Game(addr="127.0.0.1", port=1200)

# Store game
WorldInfo.game = game

#random_spawn(5)

def main(cont):  
    try:
        game.update()    
    except QuitGame:
        logic.endGame()  
        print("Ended game")
    