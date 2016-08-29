import dask.async
from threading import Thread
import time
import json

try:
    from Queue import Empty, Full, Queue # Python 2
except ImportError:
    from queue import Empty, Full, Queue # Python 3

from IPython import get_ipython

import zmq

from .base_machine import BaseMachine
from .profiler import MachineProfiler
from .exception import UpstreamError
from .util import StoppableThread, mkdir_p, json_serializable_exception, identity
from bson.objectid import ObjectId
from collections import deque
from observed import event
import warnings
import os
import sys 
import traceback
import imp


class MachineConsumer(StoppableThread):
    def __init__(self, machine, kernel_key=None):
        super(MachineConsumer, self).__init__()
        self.machine = machine
        self._socket = None
        # set local kernel key
        try:
            with open(get_ipython().config["IPKernelApp"]["connection_file"]) as f:
                config = json.load(f)
                self._kernel_key = config["key"]
        except AttributeError as ae:
            if kernel_key is not None:
                self._kernel_key = kernel_key
            else:
                self._kernel_key = str(ObjectId())
        mkdir_p("/tmp/timbr-machine") # NOTE: Not Windows Safe (but should be)
        self.initialize_pub_stream("ipc:///tmp/timbr-machine/{}".format(self._kernel_key))

    def initialize_pub_stream(self, endpoint):
        ctx = zmq.Context()
        self._socket = ctx.socket(zmq.PUB)
        self._socket.bind(endpoint)

    def run(self):
        while not self.stopped():
            try:
                # NOTE: self.get should never throw exceptions from inside the dask
                output = self.machine.get(block=True, timeout=0.1)
                hdr = output[0]
                msg = "[{}]".format(",".join(output[1:]))
                payload = [hdr, msg.encode("utf-8")]
                self.machine._status['last_oid'] = hdr
                self.machine._status['processed'] = self.machine._status['processed'] + 1
                self.machine._data_prev.append(payload)
                self._socket.send_multipart(payload)
            except Empty: # This is an instance of RemoteException, so needs to be caught first
                continue
            except dask.async.RemoteException as re: 
                # re derives from dask's RemoteException
                output = self.machine._build_output_on_error(re)
                hdr = output[0]
                msg = "[{}]".format(",".join(output[1:]))
                payload = [hdr, msg.encode("utf-8")]
                self.machine._status['errored'] = self.machine._status['errored'] + 1
                self.machine._error_prev.append(payload)
                self._socket.send_multipart(payload)
                if self.machine._debug:
                    raise

class SourceConsumer(StoppableThread):
    def __init__(self, machine, iterable):
        super(SourceConsumer, self).__init__()
        self.g = iterable
        self.machine = machine
        self._error = {}
        self._status = {}
        
    @property
    def status(self):
        _status = {"running": not self.stopped()}
        _status.update(self._error)
        return _status

    def run(self):
        while not self.stopped():
            try:
                # NOTE: next() may block which is okay but put may raise Full
                # which will interrupt the source
                msg = self.g.next()
                self.machine.put(msg)
            except (StopIteration, Full):
                self.stop()
                break
            except Exception as e:
                exc_type, exc_value, exc_traceback = sys.exc_info()
                tb = traceback.format_exception(exc_type, exc_value, exc_traceback )
                self._error = {"serialized_exception": self.machine.serialize_fn(json_serializable_exception(e, _traceback=tb))}
                self.stop()
                raise

class Machine(BaseMachine):
    def __init__(self, stages=8, bufsize=1024, debug=False):
        super(Machine, self).__init__(stages, bufsize)
        self._consumer_thread = None
        self._data_prev = deque(maxlen=10)
        self._error_prev = deque(maxlen=10)
        self._profiler = MachineProfiler()
        self._debug = debug
        self._source_thread = None

    @event
    def start(self):
        if not self.running:
            self._profiler.register()
            self._consumer_thread = MachineConsumer(self)
            self._consumer_thread.start()
        if self._source_thread is not None and not self._source_thread.is_alive():
            self._source_thread.start()

    @event
    def stop(self):
        self._consumer_thread.stop()
        self._consumer_thread.join(timeout=1.0)
        try:
            self._profiler.unregister()
        except KeyError as ke:
            pass
        if self._source_thread is not None:
            self._source_thread.stop()
            self._source_thread.join(timeout=1.0)

    @property
    def source(self):
        if self._source_thread is not None:
            return self._source_thread.g

    @source.setter
    def source(self, iterable):
        if self._source_thread is not None:
            warnings.warn("Delete existing source before reassigning")
            return
        self._source_thread = SourceConsumer(self, iterable)

    @source.deleter
    def source(self):
        if self._source_thread is not None:
            self._source_thread.stop()
            self._source_thread.join(timeout=1.0)
        self._source_thread = None
    
    @property
    def running(self):
        if self._consumer_thread is None:
            return False
        return self._consumer_thread.is_alive()

    @property
    def debug(self):
        return self._debug

    def enable_debug_mode(self):
        if self.running and not self._debug:
            warnings.warn("Debug mode cannot be enabled on a machine while it is running.")
            return
        self._debug = True

    def disable_debug_mode(self):
        self._debug = False

    def _build_output_on_error(self, e, formatter=json_serializable_exception):
        errored_task = self._profiler._errored
        tasks = [[t, t + "_s"] for t in ["oid", "in"] + ["f{}".format(i) for i in xrange(self.stages)]]
        output = []
        for fn, fn_s in tasks:
            try:
                output.append(self._profiler._cache[fn_s])
            except KeyError as ke:
                if errored_task in (fn, fn_s):
                    output.append(self.serialize_fn(formatter(e, task=errored_task)))
                else:
                    output.append(self.serialize_fn(formatter(UpstreamError(fn_s))))
        return output

    @classmethod
    def from_json(cls, config_path, init_path=None, **kwargs):
        with open(config_path, "r") as f:
            config = json.load(f)

        main = sys.modules['__main__']

        def load_machine(init_path):
            pkg_path, init = os.path.split(init_path)
        
            sys.path.append(pkg_path)
            _mod = imp.load_source("_machine_mod", init_path) 
            sys.path.pop()

            exclude = set(['__builtins__', '__doc__', '__file__', '__name__', '__package__',])
            for mod in set(dir(_mod)).difference(exclude):
                m = getattr(_mod, mod)
                setattr(main, mod, m)
        
        if init_path is not None:
            load_machine(init_path)
        elif config.get("init") is not None:
            load_machine(config["init"])
            
        _stages = max(8, len(config["functions"]))
        machine = cls(stages=_stages, **kwargs)

        for i in range(len(config["functions"])):
            if config["functions"][i] is not None:
                if config["functions"][i][0] is not None:
                    f = getattr(main, config["functions"][i][0])
                    machine[i] = f

        _source = getattr(main, config["source"][0])
        if callable(_source):
            _source = _source()
        machine.source = iter(_source)
        machine._config = config
        return machine
