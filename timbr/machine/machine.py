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
from .util import StoppableThread, mkdir_p
from .status import statushook, BaseStatus
import functools
from types import FunctionType


class MachineConsumer(StoppableThread):
    def __init__(self, machine):
        super(MachineConsumer, self).__init__()
        self.machine = machine
        self._socket = None
        # set local kernel key
        with open(get_ipython().config["IPKernelApp"]["connection_file"]) as f:
            config = json.load(f)
            self._kernel_key = config["key"]
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
                self.machine._status['LastOID'] = self.machine._status['CurrentOID']
                hdr = output[0]
                msg = "[{}]".format(",".join(output[1:]))
                # print(output)
                self._socket.send_multipart([hdr, msg.encode("utf-8")])
                self.machine._status['CurrentOID'] = hdr
                self.machine._status['Processed'] = self.machine._status['Processed'] + 1
            except Empty:
                pass


class SourceConsumer(StoppableThread):
    def __init__(self, machine, generator):
        super(SourceConsumer, self).__init__()
        self.g = generator
        self.machine = machine

    def run(self):
        while not self.stopped():
            try:
                # NOTE: next() may block which is okay but put may raise Full
                # which will interrupt the source
                msg = self.g.next()
                self.machine.put(msg)
            except (StopIteration, Full):
                break


class _Machine(BaseMachine):
    def __init__(self, stages=8, bufsize=1024, statusMixin=BaseStatus, eventMixin=None):
        super(Machine, self).__init__(stages, bufsize)
        self._consumer_thread = None

    def start(self):
        if not self.running:
            self._consumer_thread = MachineConsumer(self)
            self._consumer_thread.start()

    def stop(self):
        self._consumer_thread.stop()
        time.sleep(0.2) # give the thread a chance to stop

    def set_source(self, source_generator):
        self._source = SourceConsumer(self, source_generator)
        self._source.start()
    
    @property
    def running(self):
        if self._consumer_thread is None:
            return False
        return self._consumer_thread.is_alive()


class MachineFactory(object):
    """Returns a Machine instance with methods wrapped by given hooks"""
    baseclass = _Machine
    def __call__(self, *args, DisplayHooks=BaseDisplayHooks, EventHooks=None, **kwargs):
        machine = self.baseclass(*args, **kwargs)
        if DisplayHooks is not None:
            for m in [x[4:] for x, y in DisplayHooks.__dict__.items() if type(y) == FunctionType and x[:4]=="_on_"]:
                decorator = DisplayHooks.__getattribute__(m)
                if hasattr(machine, m) and callable(machine.__getattribute__(m)):
                    machine.__setattr__(m, decorator(machine.__getattribute__(m)))
        return machine
