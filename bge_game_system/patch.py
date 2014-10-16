from bge import logic
from game_system.resources import ResourceManager

ResourceManager.data_path = logic.expandPath("//")
ResourceManager.environment = "BGE"