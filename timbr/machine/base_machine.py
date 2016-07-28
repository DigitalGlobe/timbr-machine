from __future__ import print_function

from multiprocessing.pool import ThreadPool
import dask as da
# NOTE: sync mode wil likely be faster
# from dask.async import get_sync as get
from dask.threaded import get

_pool = ThreadPool()
da.set_options(pool=_pool)

try:
    from Queue import Empty, Full, Queue # Python 2
except ImportError:
    from queue import Empty, Full, Queue # Python 3

from bson.objectid import ObjectId
from functools import wraps, partial # should be used but isn't currently
from collections import defaultdict, deque
import inspect

import zmq
import json

from itertools import ifilter

from .util import identity, wrap_transform, json_serializable_exception, MachineProfiler



def json_serialize(obj):
    try:
        return json.dumps(obj)
    except TypeError as te:
        return json.dumps(json_serializable_exception(te))

def serialize_exception(e, **kwargs):
    emsg = {"error_": {}}
    exc  = {"exc_value": e.__repr__()}
    try:
        exc["exc_class"] = str(e.__class__)
        exc["exc_type"] = str(e.exception.__class__)
        exc["exc_tb"] = e.traceback
    except AttributeError, ae:
        pass
    emsg["error_"].update(exc)
    emsg["error_"].update(kwargs)
    return json_serialize(emsg)

def time_from_objectidstr(oid):
    return ObjectId(oid).generation_time.isoformat()

def is_serialization_task(task):
    if task[-2:] == "_s":
        return True
    return False

class MachineError(Exception):
    pass

class UpstreamException(MachineError):
    def __init__(self, fn):
        self.args = ["Task <{}> never ran due to upstream dask task error".format(fn)]
        

class BaseMachine(object):
    def __init__(self, stages=8, bufsize=1024):
        self.q = Queue(bufsize)
        self.tbl = {}
        self._status = {"last_oid": None, "processed": 0, "errored": 0, "queue_size": self.q.qsize()}
        self.stages = stages
        self.input = None
        self._dsk = None
        self._dirty = True
        self._getter = partial(get, num_workers=1)
        self._socket = None
        self._profiler = MachineProfiler()
        self._profiler.register()

        self.serialize_fn = json_serialize

        self.REFERENCE_DASK = {
            "oid_s": (str, "oid"),
            "in_s": (self.serialize_fn, "in")
        }
        self.REFERENCE_DASK.update({"f{}_s".format(i): (self.serialize_fn, "f{}".format(i)) for i in xrange(self.stages)})

    def put(self, msg):
        # NOTE: Non-blocking
        self.q.put(msg, False)

    def get(self, block=False, timeout=0.5):
        dsk = dict(self.dsk)
        dsk["in"] = (self.q.get, block, timeout)
        output = self._getter(dsk, ["oid_s", "in_s"] + ["f{}_s".format(i) for i in xrange(self.stages)])
        return output

    @property
    def status(self):
        self._status["last_processed_time"] = time_from_objectidstr(self._status["last_oid"])
        return self._status

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

    def __call__(self, data, include_serialized=False):
        dsk = dict(self.dsk)
        dsk["in"] = data
        args = ["oid", "in"] + ["f{}".format(i) for i in xrange(self.stages)]
        if include_serialized:
            args.extend(["oid_s", "in_s"] + ["f{}_s".format(i) for i in xrange(self.stages)])

        output = self._getter(dsk, args)
        return output

    @property
    def dsk(self):
        if self._dsk is None or self.dirty:
            self._dsk = {}
            self._dsk["oid"] = (ObjectId,)
            for i in xrange(self.stages):
                fkey = "f{}".format(i)
                cmd = [self.tbl.get(fkey, wrap_transform(identity))]
                cmd.extend(["f{}".format(j) for j in reversed(xrange(i)) if i > 0])
                cmd.append("in")
                cmd.extend(["f{}_s".format(j) for j in reversed(xrange(i)) if i > 0])
                cmd.append("in_s")
                self._dsk[fkey] = tuple(cmd)
            self._dsk.update(self.REFERENCE_DASK)
            self.dirty = False
        return self._dsk

    def format_status(self):
        stats = self.status
        hmap = {k: " ".join(k.split("_")).upper() for k in stats.keys()}
        s = ""
        for h in sorted(stats.keys()):
            s += "{:<5} --- {:<5}\n\n".format(hmap[h], stats[h])
        return s

    def print_status(self):
        print(self.format_status())

    def _build_output_on_error(self, e, e_serializer=serialize_exception):
        errored_task = self._profiler._errored
        tasks = [[t, t + "_s"] for t in ["oid", "in"] + ["f{}".format(i) for i in xrange(self.stages)]]
        output = []
        for fn, fn_s in tasks:
            try:
                output.append(self._profiler._cache[fn_s])
            except KeyError as ke:
                if errored_task in (fn, fn_s):
                    output.append(e_serializer(e, task=errored_task))
                else:
                    output.append(e_serializer(upstream_exception(fn_s)))
        return output      
