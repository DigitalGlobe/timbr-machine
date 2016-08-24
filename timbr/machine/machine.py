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
from .util import StoppableThread, mkdir_p, json_serializable_exception
from bson.objectid import ObjectId
from collections import deque
from observed import event
import warnings
import os, sys, traceback


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
    def __init__(self, machine, generator):
        super(SourceConsumer, self).__init__()
        self.g = generator
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
        self.source = None

    @event
    def start(self):
        if not self.running:
            self._profiler.register()
            self._consumer_thread = MachineConsumer(self)
            self._consumer_thread.start()

    @event
    def stop(self):
        self._consumer_thread.stop()
        self._consumer_thread.join(timeout=1.0)
        try:
            self._profiler.unregister()
        except KeyError as ke:
            pass

    def set_source(self, source_generator):
        self.source = SourceConsumer(self, source_generator)
        
    def start_source(self):
        if self.source is not None:
            self.source.start()

    def stop_source(self):
        self.source.stop()
        self.source.join(timeout=1.0)
    
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
    def machine_from_json(cls, config_path=None, **kwargs):
        if config_path is None:
            config_path = os.path.join(os.getcwd(), "machine.json")
        with open(config_path, "r") as f:
            config = json.load(f)
        _module_path = config["_module_path"]
        sys.path.append(_module_path)
        import _machine_
        machine = cls(**kwargs)
        if config.get("source") is not None:
            _source = getattr(_machine_, "_source")
            machine.set_source(_source())
        for ind in range(len(config["transforms"])):
            f = getattr(_machine_, "_f{}".format(ind))
            machine[ind] = f            
        machine._config = config
        return machine








