from game_system.controllers import PlayerControllerBase

from .audio import AUDAudioManager
from .inputs import BGEMouseManager, BGEInputStatusLookup

__all__ = ["PlayerController"]


class PlayerController(PlayerControllerBase):

    audio_manager_class = AUDAudioManager
    input_lookup_class = BGEInputStatusLookup
    mouse_manager_class = BGEMouseManager