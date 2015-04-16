__all__ = "LevelManager",


class LevelManager:

    def __init__(self):
        self._state = set()

        self.on_enter = None
        self.on_exit = None

    def __bool__(self):
        return bool(self._state)

    def _on_enter(self, event):
        if callable(self.on_enter):
            self.on_enter(event)

    def _on_exit(self, event):
        if callable(self.on_exit):
            self.on_exit(event)

    def add(self, event):
        if event not in self._state:
            self._on_enter(event)

        self._state.add(event)

    def remove(self, event):
        self._on_exit(event)
        self._state.remove(event)