import threading
import queue
import time

from .proxy import Proxy


class SafeProxy(Proxy):

    def __del__(self):
        object.__getattribute__(self, "_obj").join()


class QueuedThread(threading.Thread):
    """
    A sample thread class
    """

    def __init__(self):
        threading._time = time.monotonic

        self.in_queue = queue.Queue()
        self.out_queue = queue.Queue()

        self._event = threading.Event()
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

            except queue.Empty:
                continue
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
