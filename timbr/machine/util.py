
from dask.callbacks import Callback

from collections import namedtuple
from itertools import starmap
from timeit import default_timer

import threading
import inspect

# Stolen from StackOverflow:
# http://stackoverflow.com/questions/323972/is-there-any-way-to-kill-a-thread-in-python
class StoppableThread(threading.Thread):
    """Thread class with a stop() method. The thread itself has to check
    regularly for the stopped() condition."""

    def __init__(self):
        super(StoppableThread, self).__init__()
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()

    def stopped(self):
        return self._stop.isSet()


def identity(x):
    return x


def wrap_transform(fn):
    """
    This function returns a new function that accepts 
    an arbitrary number of arguments
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
        # print("called with {}".format(str(args)))
        return fn(*args[:nargs])
    return wrapped


def json_serializable_exception(e, extra_data={}):
    #extra_data["_traceback"] = tb.format_tb(e)
    #extra_data["_exception"] = tb.format_exception_only(e)
    extra_data["_exception"] = str(e)
    #extra_data["_exception_dict"] = e.__dict__
    return(extra_data)

import os, errno

def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc: # Python >2.5
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else: raise

class OrderedDefaultDict(OrderedDict):
    def __init__(self, default_factory, *args, **kwargs):
        super(OrderedDefaultDict, self).__init__(*args, **kwargs)
        assert callable(default_factory)
        self.default_factory = default_factory
        
    def __getitem__(self, key):
        try:
            return super(OrderedDefaultDict, self).__getitem__(key)
        except KeyError:
            return self.__missing__(key)

    def __missing__(self, key):
        if self.default_factory is None:
            raise KeyError(key)
        self[key] = value = self.default_factory()
        return value



TaskData = namedtuple('TaskData', ('key', 'task', 'start_time',
                                   'end_time', 'worker_id'))


class MachineProfiler(Callback):
    """A profiler for dask execution at the task level.

    If you use the profiler globally you will need to clear out old results
    manually.
    >>> prof.clear()
    """
    def __init__(self):
        self._dsk = {}
        self._successful = []
        self._current = None
        self._errored = None
        self._cache = None

    def __enter__(self):
        self.clear()
        return super(MachineProfiler, self).__enter__()

    def _start(self, dsk):
        self._dsk.update(dsk)

    def _pretask(self, key, dsk, state):
        # state is a dict
        self._current = key

    def _posttask(self, key, value, dsk, state, id):
        self._successful.append(key)

    def _finish(self, dsk, state, failed):
        if failed:
            self._errored = self._current
            self._cache = state["cache"].copy()
            
    def clear(self):
        """Clear out old results from profiler"""
        del self._successful[:]
        self._current = None
        self._errored = None
        self._cache = None
        self._dsk = {}
