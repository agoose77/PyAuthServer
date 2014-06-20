__all__ = ["ISoundHandle", "IAudioManager"]


class ISoundHandle:

    def stop(self):
        raise NotImplementedError()

    def start(self):
        raise NotImplementedError()


class IAudioManager:

    @property
    def listener_location(self):
        raise NotImplementedError()

    @listener_location.setter
    def listener_location(self, value):
        raise NotImplementedError()

    @property
    def listener_orientation(self):
        raise NotImplementedError()

    @listener_orientation.setter
    def listener_orientation(self, value):
        raise NotImplementedError()

    @property
    def listener_velocity(self):
        raise NotImplementedError()

    @listener_velocity.setter
    def listener_velocity(self, value):
        raise NotImplementedError()

    @property
    def distance_model(self):
        raise NotImplementedError()

    @distance_model.setter
    def distance_model(self, value):
        raise NotImplementedError()

    def play_sound(self, sound_path):
        raise NotImplementedError()