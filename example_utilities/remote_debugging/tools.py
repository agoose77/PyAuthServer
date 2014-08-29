import sys

from io import StringIO
from contextlib import contextmanager

@contextmanager
def stdout_io(stdout=None):
    old = sys.stdout
    if stdout is None:
        stdout = StringIO()
        
    sys.stdout = stdout
    yield stdout
    sys.stdout = old


def input_multiple(cmd):
    results = []
    while True:
        result = input("[{}] {}".format(len(results), cmd))
        if result == "":
            break

        results.append(result)

    return '\n'.join(results)
