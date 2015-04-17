__all__ = "LevelManager",


class LevelManager:

    def __init__(self):
        self._state = set()

        self.on_enter = None
        self.on_exit = None

    def __bool__(self):
        return bool(self._state)

    def _on_enter(self, event, *args, **kwargs):
        if callable(self.on_enter):
            self.on_enter(event, *args, **kwargs)

    def _on_exit(self, event, *args, **kwargs):
        if callable(self.on_exit):
            self.on_exit(event, *args, **kwargs)

    def add(self, event, *args, **kwargs):
        if event not in self._state:
            self._on_enter(event, *args, **kwargs)

        self._state.add(event)

    def remove(self, event):
        try:
            self._state.remove(event)

        except KeyError:
            return

        self._on_exit(event)