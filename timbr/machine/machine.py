import six

from threading import Thread, Lock, Event, ThreadError
from dask.multiprocessing import RemoteException
import time
import json
import warnings

try:
    from Queue import Empty, Full, Queue # Python 2
except ImportError:
    from queue import Empty, Full, Queue # Python 3

from IPython import get_ipython

import zmq

from timbr.machine.base_machine import BaseMachine
from timbr.machine.profiler import MachineProfiler
from timbr.machine.exception import UpstreamError
from timbr.machine.util import StoppableThread, mkdir_p, json_serializable_exception, identity, in_ipython_runtime_env
from bson.objectid import ObjectId
from collections import deque
#from observed import event
import warnings
import os
import sys
import traceback
import imp

IN_IPYTHON_RUNTIME = in_ipython_runtime_env()
levels = ["ERROR", "WARNING", "INFO"]

def _get_traceback():
    exc_type, exc_value, exc_traceback = sys.exc_info()
    tb = traceback.format_exception(exc_type, exc_value, exc_traceback)
    return tb

def _format_dispatch_emsg(inst, level="ERROR", **kwargs):
    m = {"origin": str(inst)}
    m["level"] = level
    m.update(**kwargs)
    return m

class IPythonPluginFactory(type):
    def __new__(cls, name, bases, attrs):
        if IN_IPYTHON_RUNTIME:
            from timbr.extensions.ipy import IPythonMachineMixin
            bases = list(bases)
            bases.append(IPythonMachineMixin)
            bases = tuple(bases)
        return type.__new__(cls, name, bases, attrs)


class MachineConsumer(StoppableThread):
    def __init__(self, machine, kernel_key=None):
        super(MachineConsumer, self).__init__()
        self.machine = machine
        self._socket = None
        self._trigger = Event()
        self.trigger()
        self._dispatched = []
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

    def __str__(self):
        return "MachineConsumer"

    def trigger(self):
         self._trigger.set()

    def pause(self):
        self._trigger.clear()

    def paused(self):
        return not self._trigger.isSet()

    def initialize_pub_stream(self, endpoint):
        ctx = zmq.Context()
        self._socket = ctx.socket(zmq.PUB)
        self._socket.bind(endpoint)

    def _dispatch_err(self, e, **kwargs):
        if hasattr(self.machine, "dispatch"):
            m = {"location": self.machine._profiler._errored}
            m["exc_class"] = str(e.__class__)
            m["exc_type"] = str(e.exception.__class__)
            m["exc_tb"] = _get_traceback()
            m["exc_value"] = e.__repr__()
            dmsg = _format_dispatch_emsg(self, **kwargs)
            emsg = {"exception": m}
            dmsg.update(emsg)
            self.machine.dispatch(self.machine.serialize_fn(dmsg))
        else:
            pass # Should we do something else here?

    def run(self):
        while not self.stopped():
            self._trigger.wait() # Wait for this flag to be set to Fal
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
            except RemoteException as re:
                # re derives from dask's RemoteException
                output = self.machine._build_output_on_error(re)
                hdr = output[0]
                msg = "[{}]".format(",".join(output[1:]))
                payload = [hdr, msg.encode("utf-8")]
                self.machine._status['errored'] = self.machine._status['errored'] + 1
                self.machine._error_prev.append(payload)
                self._socket.send_multipart(payload)
                self._dispatch_err(re)
                if self.machine._debug:
                    raise

class SourceConsumer(StoppableThread):
    def __init__(self, machine, iterable):
        super(SourceConsumer, self).__init__()
        self.g = iterable
        self.machine = machine
        self._exhausted = False # naive
        self._full = False # naive
        self._error = {}
        self._status = {}

    def __str__(self):
        return "SourceConsumer"

    @property
    def status(self):
        _status = {"running": self.is_alive(), "exhausted": self._exhausted, "full": self._full}
        _status.update(self._error)
        return _status

    def _dispatch_err(self, e, **kwargs):
        if hasattr(self.machine, "dispatch"):
            m = {}
            m["location"] = "source"
            m["exc_class"] = str(e.__class__)
            m["exc_type"] = str(type(e))
            m["exc_tb"] = _get_traceback()
            m["exc_value"] = e.__repr__()
            dmsg = _format_dispatch_emsg(self, **kwargs)
            emsg = {"exception": m}
            dmsg.update(emsg)
            self.machine.dispatch(self.machine.serialize_fn(dmsg))
        else:
            pass # Should we do something else here?

    def run(self):
        while not self.stopped():
            try:
                # NOTE: next() may block which is okay but put may raise Full
                # which will interrupt the source
                msg = next(self.g)
                self.machine.put(msg)
            except (StopIteration, Full) as e:
                errored = True
                if isinstance(e, StopIteration):
                    self._exhausted = True
                else:
                    self._full = True
                self._dispatch_err(e, level="INFO")
                self.stop()
                break
            except Exception as e:
                self._dispatch_err(e)
                tb = _get_traceback
                self._error = {"serialized_exception":
                               self.machine.serialize_fn(json_serializable_exception(e, _traceback=tb))}
                self.stop()
                raise

@six.add_metaclass(IPythonPluginFactory)
class Machine(BaseMachine):
    def __init__(self, stages=8, bufsize=1024, start_consumer=True, debug=False):
        super(Machine, self).__init__(stages, bufsize)
        self._consumer_thread = None
        self._data_prev = deque(maxlen=10)
        self._error_prev = deque(maxlen=10)
        self._profiler = MachineProfiler()
        self._debug = debug
        self._source_thread = None
        if start_consumer:
            self.start()

    def __str__(self):
        return "Machine"

#    @event
    def start(self):
        if self._consumer_thread is None or not self._consumer_thread.is_alive():
            self._profiler.register()
            self._consumer_thread = MachineConsumer(self)
            self._consumer_thread.start()
        # Unpause consumer if paused:
        if self._consumer_thread.paused():
            self._consumer_thread.trigger()

        if self._source_thread is not None and not self._source_thread.is_alive():
            try:
                self._source_thread.start()
                return
            except RuntimeError as re: # The thread has already been started and has been stopped for some reason
                status = self._source_thread.status
                if not (status.get("exhausted") or status.get("full") or status.get("serialized_exception") is not None):
                    g = self.source # Attempt to restart the source generator in a new thread if we can, otherwise do nothing
                    del self.source
                    self.source = g
                    self._source_thread.start()
                return

#    @event
    def stop(self, clear_buffer=True, hard_stop=False):
        if self._consumer_thread is not None and self._consumer_thread.is_alive():
            is_paused = self._consumer_thread.paused()
            if hard_stop:
                if is_paused:
                    self._consumer_thread.trigger() # have to unpause to join on run
                self._consumer_thread.stop()
                self._consumer_thread.join(timeout=1.0)
                try:
                    self._profiler.unregister()
                except KeyError as ke:
                    pass
            else:
                if not is_paused:
                    self._consumer_thread.pause() # otherwise pause consumer if not already

        if self._source_thread is not None and self._source_thread.is_alive():
            self._source_thread.stop()
            self._source_thread.join(timeout=1.0)

        if clear_buffer:
            self.q._init(self._bufsize)

    def _dispatch_err(self, e, **kwargs):
        if hasattr(self, "dispatch"):
            m = {"location": "Machine"}
            m["exc_class"] = str(e.__class__)
            m["exc_type"] = str(type(e))
            m["exc_tb"] = _get_traceback()
            m["exc_value"] = e.__repr__()
            dmsg = _format_dispatch_emsg(self, **kwargs)
            emsg = {"exception": m}
            dmsg.update(emsg)
            self.dispatch(self.serialize_fn(dmsg))
        else:
            pass # Should we do something else here?

    @property
    def source(self):
        if self._source_thread is not None:
            return self._source_thread.g

    @source.setter
    def source(self, source):
        if self._source_thread is not None:
            warnings.warn("Delete existing source before reassigning")
            return
        if callable(source):
            source = source()
        source = iter(source)
        self._source_thread = SourceConsumer(self, source)

    @source.deleter
    def source(self):
        if self._source_thread is not None and self._source_thread.is_alive():
            self._source_thread.stop()
            self._source_thread.join(timeout=1.0)

        self._source_thread = None
        self._data_prev.clear()
        self._error_prev.clear()

    @property
    def active(self):
        if self._consumer_thread is None:
            return False
        return self._consumer_thread.is_alive() and not self._consumer_thread.paused()

    @property
    def processing(self):
        if self.active and self._source_thread is not None:
            return self._source_thread.is_alive()
        return False

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
        tasks = [[t, t + "_s"] for t in ["oid", "in"] + ["f{}".format(i) for i in range(self.stages)]]
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


        return self.serialize_fn(json_serializable_exception(e, _traceback=tb, **kwargs))

    def _configure(self, config):
        assert self.source is None
        self._config = config

        main = sys.modules['__main__']

        for i in range(len(config["functions"])):
            if config["functions"][i] is not None:
                if config["functions"][i][0] is not None:
                    f = getattr(main, config["functions"][i][0])
                    self[i] = f

        if len(config["source"]) > 0:
            _source = getattr(main, config["source"][0])
            if callable(_source):
                if _source.__code__.co_argcount > 0:
                    return self # This implies that user needs to instantiate generator function w/ args
                _source = _source()
            self.source = iter(_source)

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
        machine._config = config

        for i in range(len(config["functions"])):
            if config["functions"][i] is not None:
                if config["functions"][i][0] is not None:
                    f = getattr(main, config["functions"][i][0])
                    machine[i] = f

        if len(config["source"]) > 0:
            _source = getattr(main, config["source"][0])
            if callable(_source):
                if _source.__code__.co_argcount > 0:
                    return machine # This implies that user needs to instantiate generator function w/ args
                _source = _source()
            machine.source = iter(_source)

        return machine

    @classmethod
    def from_project(cls, project_path):
        try:
            assert os.path.exists(project_path)
            if os.path.isfile(os.path.join(project_path, 'machine.json')):
                config_file = os.path.join(project_path, 'machine.json')
                init_file = os.path.join(project_path, '__init__.py')
                return cls.from_json(config_file, init_path=init_file)
            else:
                return cls()
        except Exception as e:
            raise EnvironmentError("Unexpected project structure and/or content.\n{}".format(e.message))

    @classmethod
    def load_machine(cls):
        try:
            prj_path = os.environ['TIMBR_PROJECT']
            if not os.path.exists(prj_path):
                os.makedirs(prj_path)
            return cls.from_project(prj_path)
        except KeyError:
            warnings.warn("TIMBR_PROJECT not defined, instatiating empty Machine")
            return cls()
        except EnvironmentError:
            warnings.warn("Invalid Project, instantiating empty Machine")
            return cls()
        except Exception as e:
            warnings.warn("Unknown Error initializing machine:\n{}".format(e.message))
            return cls()
