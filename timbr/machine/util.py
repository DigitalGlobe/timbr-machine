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

def display_status(status, detailed=False, inspect=None):
    from IPython.display import Image, HTML, display
    
    stats = MACHINE.status
    s0 = "<div style='border:1px; border-style:solid; width:400px; height:auto; float:left;'><b>Current Ingest Time -- {}</b></div>".format(stats['CurrentTime'])
    s1 = "<div style='border:1px; border-style:solid; width:400px; height:auto; float:left;'><b>Current Ingest ID -- {}</b></div>".format(stats['CurrentOID'])
    s2 = "<div style='border:1px; border-style:solid; width:400px; height:auto; float:left;'><b>Total Datum Processed -- {}</b></div>".format(stats['Processed'])
    s3 = "<div style='border:1px; border-style:solid; width:400px; height:auto; float:left;'><b>Current Queue Depth -- {}</b></div>".format(stats["QueueSize"])
    display(HTML("\n".join([s0, s1, s2, s3])))

    headers = ["Function", "Number of Errors", "Error Types"]
