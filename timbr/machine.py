from multiprocessing.pool import ThreadPool
from dask.threaded import get

_pool = ThreadPool()
da.set_options(pool=_pool)

try:
    from Queue import Empty, Full, Queue # Python 2
except ImportError:
    from queue import Empty, Full, Queue # Python 3

from bson.objectid import ObjectId
from functools import wraps # should be used but isn't currently
import inspect

def identity(x):
    return x


def wrap_transform(fn):
    """
    This function returns a new function that accepts an arbitrary number of arguments
    and calls the wrapped function with the number of arguments that it supports. For
    example:

    def f(a, b):
        ...

    g = wrap_transform(f)

    assert g(a, b, c, d) == f(a, b)

    """
    assert callable(fn)
    try:
        info = inspect.getargspec(fn)
        nargs = len(info.args)
    except TypeError:
        # fallback to pipeline mode
        nargs = 1
    def wrapped(*args, **kwargs):
        # print "called with {}".format(str(args))
        return fn(*args[:nargs])
    return wrapped



class Machine(object):
    def __init__(self, stages=8, bufsize=1024):
        self.q = Queue(bufsize)
        self.tbl = {}
        self.stages = stages
        self._dsk = None
        self._dirty = True
        self._getter = get

    def put(self, msg):
        # NOTE: Non-blocking
        self.q.put(msg, False)

    def get(self):
        # TODO: trap error conditions (here?)
        return self._getter(self.dsk, ["oid", "in"] + ["f{}".format(i) for i in xrange(self.stages)])

    def __len__(self):
        return stages

    def __setitem__(self, pos, fn):
        assert isinstance(pos, (int, long))
        assert pos >=0 and pos < self.stages
        wrapped_fn = wrap_transform(fn)
        self.tbl["f{}".format(pos)] = wrapped_fn
        self.dirty = True

    def __getitem__(self, pos):
        assert isinstance(pos, (int, long))
        assert pos >=0 and pos < self.stages
        return self.tbl["f{}".format(pos)]

    def __missing__(self, pos):
        return wrap_transform(identity)

    def __delitem__(self, pos):
        assert isinstance(pos, (int, long))
        assert pos >=0 and pos < self.stages
        del self.tbl["f{}".format(pos)]
        self.dirty = True

    def __call__(self, data):
        dsk = dict(self.dsk)
        dsk["in"] = data
        return self._getter(dsk, ["in"] + ["f{}".format(i) for i in xrange(self.stages)])

    @property
    def dsk(self):
        if self._dsk is None or self.dirty:
            self._dsk = {}
            self._dsk["oid"] = (ObjectId,)
            self._dsk["in"] = (self.q.get, False)
            for i in xrange(self.stages):
                fkey = "f{}".format(i)
                self._dsk[fkey] = tuple([self.tbl.get(fkey, wrap_transform(identity))] +
                                  ["f{}".format(j) for j in reversed(xrange(i)) if i > 0] +
                                  ["in"])
                self
            self.dirty = False
        return self._dsk
