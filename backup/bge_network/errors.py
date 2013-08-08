'''
Created on 11 Apr 2013

@author: Angus
'''
from network import NetworkError

class PlayerLimitReached(NetworkError):
    pass

class QuitGame(NetworkError):
    pass