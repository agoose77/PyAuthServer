import threading
import queue
import time

class ThreadPointer():

    def __init__(self, thread):
        self._thread = thread

    def __del__(self):
        self._thread.join()


class QueuedThread(threading.Thread):
    """
    A sample thread class
    """

    def __init__(self):
        threading._time = time.clock

        self.in_queue = queue.Queue()
        self.out_queue = queue.Queue()

        self._event = threading.Event()
        self._poll_interval = 1 / 60

        super().__init__()

    def handle_task(self, task, queue):
        pass

    def run(self):
        is_empty = queue.Empty
        while not self._event.isSet():

            try:
                item = self.in_queue.get(True, self._poll_interval)

            except is_empty:
                continue

            try:
                self.handle_task(item, self.out_queue)
            except Exception as err:
                print(err)

    def join(self, timeout=None):
        self._event.set()
        super().join(timeout)
