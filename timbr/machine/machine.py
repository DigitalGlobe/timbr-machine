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
from .util import StoppableThread


class MachineConsumer(StoppableThread):
    def __init__(self, machine):
        super(MachineConsumer, self).__init__()
        self.machine = machine
        self._socket = None
        # set local kernel key
        with open(get_ipython().config["IPKernelApp"]["connection_file"]) as f:
            config = json.load(f)
            self._kernel_key = config["key"]
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
                print(output)
                # TODO: serialize and send over the zmq socket (self._socket)
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


class Machine(BaseMachine):
    def __init__(self, stages=8, bufsize=1024):
        super(Machine, self).__init__(stages, bufsize)
        self._consumer_thread = None
        self._running = False

    def start(self):
        if not self._running:
            self._consumer_thread = MachineConsumer(self)
            self._consumer_thread.start()
            self._running = True

    def stop(self):
        self._consumer_thread.stop()
        time.sleep(0.2) # give the thread a chance to stop
        self._running = False

    def set_source(self, source_generator):
        self._source = SourceConsumer(self, source_generator)
        self._source.start()
        return self._source
