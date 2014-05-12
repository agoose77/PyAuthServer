from queue import Queue, Empty
from threading import Event, Thread

from .proxy import Proxy


__all__ = ["SafeProxy", "QueuedThread", "SafeThread"]


class SafeProxy(Proxy):

    def __del__(self):
        object.__getattribute__(self, "_obj").join()


class QueuedThread(Thread):
    """
    A sample thread class
    """

    def __init__(self):
        self.in_queue = Queue()
        self.out_queue = Queue()

        self._event = Event()
        self._poll_interval = 1 / 60

        super().__init__()

    def handle_task(self, task, queue):
        pass

    def get_task(self, poll_interval, queue):
        return queue.get(True, poll_interval)

    def run(self):
        while not self._event.isSet():

            try:
                item = self.get_task(self._poll_interval, self.in_queue)

            except Empty:
                continue

            except Exception as err:
                print(err)
                break

            try:
                self.handle_task(item, self.out_queue)

            except Exception as err:
                print(err)
                break

    def join(self, timeout=None):
        self._event.set()

        super().join(timeout)


class SafeThread(QueuedThread):

    def __new__(cls, *args, **kwargs):
        obj = super().__new__(cls, *args, **kwargs)
        obj.__init__(*args, **kwargs)

        return SafeProxy(obj)
