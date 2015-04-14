"""Import before instantiation of runtime-resolved types in game_system module.

Sets the data path and environment variables for Panda3D Game Engine
"""
from os import getcwd, path
from game_system.resources import ResourceManager

ResourceManager.data_path = path.join(getcwd(), "data")
ResourceManager.environment = "Panda"