import sys

def assertrefs(ob, r):
    count = (sys.getrefcount(ob) - 2)
    assert count == r, "Too {} references found!".format("many" if count > r else "few")

try:
    assertrefs(object(), 1)
    a = object()
    assertrefs(a, 2)
except AssertionError:
    raise ImportError("Module does not function correctly")