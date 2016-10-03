import threading

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

import inspect

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

import os
import errno

def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc: # Python >2.5
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else: raise

# Modifed from StackOverflow:
# http://stackoverflow.com/questions/12700893/how-to-check-if-a-string-is-a-valid-python-identifier-including-keyword-check

import ast
import types 

def isidentifier(ident):
    """Determines, if string is valid Python identifier."""

    # Smoke test - if it's not string, then it's not identifier, but we
    # want to just silence exception. It's better to fail fast.
    if not isinstance(ident, types.StringTypes):
        raise TypeError('expected str, but got {!r}'.format(type(ident)))

    # Resulting AST of simple identifier is <Module [<Expr <Name "foo">>]>
    try:
        root = ast.parse(ident)
    except SyntaxError:
        return False

    if not isinstance(root, ast.Module):
        return False

    if len(root.body) != 1:
        return False

    if not isinstance(root.body[0], ast.Expr):
        return False

    if not isinstance(root.body[0].value, ast.Name):
        return False

    if root.body[0].value.id != ident:
        return False

    return True

import re

def camelcase_to_underscored(string):
    """ camelCase to Pythonic naming """
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', string)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()

from timbr.machine import serializer

def make_wamp_safe(obj):
    """ Crappy way of forcing an object that is safe for our serializer to be ok for the Autobahn WAMP one """
    return serializer.wamp_safe_loads(serializer.dumps(obj))

from collections import namedtuple, OrderedDict

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

