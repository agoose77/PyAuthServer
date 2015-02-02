"""Import before instantiation of runtime-resolved types in game_system module.

Sets the data path and environment variables for Blender Game Engine
"""
from bge import logic
from game_system.resources import ResourceManager

ResourceManager.data_path = logic.expandPath("//data")
ResourceManager.environment = "BGE"