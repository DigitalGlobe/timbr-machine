from IPython import get_ipython

from multiprocessing.pool import ThreadPool
import dask as da
#from dask.async import get_sync as get
from dask.threaded import get # NOTE: sync mode wil likely be faster

_pool = ThreadPool()
da.set_options(pool=_pool)

try:
    from Queue import Empty, Full, Queue # Python 2
except ImportError:
    from queue import Empty, Full, Queue # Python 3

from bson.objectid import ObjectId
from functools import wraps # should be used but isn't currently
import inspect

import zmq
import json

from .util import identity, wrap_transform, json_serializable_exception


def json_serialize(obj):
    try:
        return json.dumps(obj)
    except TypeError as te:
        return json.dumps(json_serializable_exception(te))


class BaseMachine(object):
    def __init__(self, stages=8, bufsize=1024):
        self.q = Queue(bufsize)
        self.tbl = {}
        self.stages = stages
        self._dsk = None
        self._dirty = True
        self._getter = get
        self._socket = None


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
