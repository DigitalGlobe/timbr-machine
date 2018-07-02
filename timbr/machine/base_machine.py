from __future__ import print_function
from timbr.compat import PY3, int

import dask
# NOTE: sync mode wil likely be faster

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

from timbr.machine.util import identity, wrap_transform, json_serializable_exception
from timbr.machine.profiler import MachineProfiler
from timbr.machine.exception import UpstreamError

def json_serialize(obj):
    try:
        return json.dumps(obj)
    except TypeError as te:
        return json.dumps(json_serializable_exception(te))

def time_from_objectidstr(oid):
    return ObjectId(oid).generation_time.isoformat()

def is_serialization_task(task):
    if task[-2:] == "_s":
        return True
    return False


class BaseMachine(object):
    def __init__(self, stages=8, bufsize=1024, serialize_fn=json_serialize, num_workers=1):
        self.q = Queue(bufsize)
        self._bufsize = bufsize
        self.tbl = {}
        self._status = {"last_oid": None, "processed": 0, "errored": 0, "queue_size": self.q.qsize()}
        self.stages = stages
        self._dsk = None
        self._dirty = True
        self._getter = partial(dask.threaded.get, num_workers=num_workers)
        self.dispatcher = None

        self.serialize_fn = serialize_fn

        self.REFERENCE_DASK = {
            "oid_s": (str, "oid"),
            "in_s": (self.serialize_fn, "in")
        }
        self.REFERENCE_DASK.update({"f{}_s".format(i): (self.serialize_fn, "f{}".format(i)) for i in range(self.stages)})

    def put(self, msg):
        # NOTE: Non-blocking
        self.q.put(msg, False)

    def get(self, block=False, timeout=0.5):
        dsk = dict(self.dsk)
        dsk["in"] = (self.q.get, block, timeout)
        output = self._getter(dsk, ["oid_s", "in_s"] + ["f{}_s".format(i) for i in range(self.stages)])
        return output

    @property
    def status(self):
        self._status["last_processed_time"] = time_from_objectidstr(self._status["last_oid"])
        self._status["queue_size"] = self.q.qsize()
        return self._status

    def __len__(self):
        return self.stages

    def __setitem__(self, pos, fn):
        assert isinstance(pos, int)
        assert pos >=0 and pos < self.stages
        wrapped_fn = wrap_transform(fn)
        self.tbl["f{}".format(pos)] = wrapped_fn
        self.dirty = True

    def __getitem__(self, pos):
        assert isinstance(pos, int)
        assert pos >=0 and pos < self.stages
        return self.tbl["f{}".format(pos)]

    def __missing__(self, pos):
        return wrap_transform(identity)

    def __delitem__(self, pos):
        assert isinstance(pos, int)
        assert pos >=0 and pos < self.stages
        del self.tbl["f{}".format(pos)]
        self.dirty = True

    def __call__(self, data, include_serialized=False):
        dsk = dict(self.dsk)
        dsk["in"] = data
        args = ["oid", "in"] + ["f{}".format(i) for i in range(self.stages)]
        if include_serialized:
            args.extend(["oid_s", "in_s"] + ["f{}_s".format(i) for i in range(self.stages)])

        output = self._getter(dsk, args)
        return output

    @property
    def dsk(self):
        if self._dsk is None or self.dirty:
            self._dsk = {}
            self._dsk["oid"] = (ObjectId,)
            for i in range(self.stages):
                fkey = "f{}".format(i)
                cmd = [self.tbl.get(fkey, wrap_transform(identity))]
                cmd.extend(["f{}".format(j) for j in reversed(range(i)) if i > 0])
                cmd.append("in")
                cmd.extend(["f{}_s".format(j) for j in reversed(range(i)) if i > 0])
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
