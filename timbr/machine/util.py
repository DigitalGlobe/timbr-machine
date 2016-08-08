
from collections import namedtuple, OrderedDict
from itertools import starmap

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


def json_serializable_exception(e, **kwargs):
    emsg = {"_exception": {}}
    exc  = {"exc_value": e.__repr__()}
    try:
        exc["exc_class"] = str(e.__class__)
        exc["exc_type"] = str(e.exception.__class__)
        exc["exc_tb"] = e.traceback
    except AttributeError, ae:
        pass
    emsg["_exception"].update(exc)
    emsg["_exception"].update(kwargs)
    return emsg

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

