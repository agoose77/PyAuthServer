from game_system.audio import IAudioManager

from aud import device, Factory

_all__ = ["AUDAudioManager", "AUDSoundHandle"]


class AUDSoundHandle:

    def __init__(self, handle):
        self._handle = handle

    def stop(self):
        self._handle.stop()

    def pause(self):
        self._handle.pause()

    def resume(self):
        self._handle.resume()


class AUDAudioManager:

    def __init__(self):
        self._device = device()

    @property
    def listener_location(self):
        return self._device.listener_location

    @listener_location.setter
    def listener_location(self, value):
        self._device.listener_location = value

    @property
    def listener_orientation(self):
        return self._device.listener_orientation

    @listener_orientation.setter
    def listener_orientation(self, value):
        self._device.listener_orientation = value

    @property
    def listener_velocity(self):
        return self._device.listener_velocity

    @listener_velocity.setter
    def listener_velocity(self, value):
        self._device.listener_velocity = value

    @property
    def distance_model(self):
        return self._device.distance_model

    @distance_model.setter
    def distance_model(self, value):
        self._device.distance_model = value

    def play_sound(self, sound_path):
        factory = Factory(sound_path)
        handle = device.play(factory)
        return AUDSoundHandle(handle)