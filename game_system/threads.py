from contextlib import contextmanager
from queue import Queue, Empty
from threading import Event, Thread

from .proxy import Proxy


__all__ = ["SafeProxy", "QueuedThread", "SafeThread"]


class SafeProxy(Proxy):

    def __del__(self):
        obj = object.__getattribute__(self, "_obj")
        obj.join()


class ThreadDataInterface:

    def __init__(self, requests, commits, timeout=0.0):
        self.requests = requests
        self.commits = commits
        self._timeout = timeout

    def commit(self, task):
        self.commits.put(task, timeout=self._timeout)

    @contextmanager
    def guarded_request(self):
        item = self.request()

        yield item

        if item is not None:
            self.on_request_complete()

    def on_request_complete(self):
        self.requests.task_done()

    def request(self):
        try:
            item = self.requests.get(timeout=self._timeout)

        except Empty:
            return

        return item


class QueuedThread(Thread):
    """
    A sample thread class
    """

    def __init__(self):
        self._queue_a = Queue()
        self._queue_b = Queue()

        self.client = ThreadDataInterface(self._queue_a, self._queue_b)
        self.slave = ThreadDataInterface(self._queue_b, self._queue_a, timeout=1/30)

        self._event = Event()

        super().__init__()

    def handle_task(self):
        """Remove a task from the input queue, perform some operations and place result in output queue"""
        pass

    def run(self):
        while not self._event.isSet():
            try:
                self.handle_task()

            except Exception:
                import traceback
                traceback.print_exc()
                break

    def join(self, timeout=None):
        self._event.set()

        super().join(timeout)


class SafeThread(QueuedThread):

    def __new__(cls, *args, **kwargs):
        obj = super().__new__(cls, *args, **kwargs)
        obj.__init__(*args, **kwargs)

        return SafeProxy(obj)
