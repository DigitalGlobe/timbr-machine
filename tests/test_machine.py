import unittest
from mock import MagicMock, call

from timbr.machine.base_machine import BaseMachine, json_serialize
from timbr.machine import Machine 
from timbr.machine.machine import SourceConsumer, MachineConsumer

try:
    from Queue import Empty, Full, Queue # Python 2
except ImportError:
    from queue import Empty, Full, Queue # Python 3

import dask.async
from dask.threaded import get
import functools
from timbr.machine.util import identity, wrap_transform, json_serializable_exception, StoppableThread
from timbr.machine.profiler import MachineProfiler
from bson.objectid import ObjectId
import time
import random


def configurable_gn(s, t):
    for i in xrange(s):
        yield i
        time.sleep(t)

class MockMachine(object):
    def put(self, x):
        pass

class TestSourceConsumer(unittest.TestCase):
    def setUp(self):
        self.mm = MockMachine()
        self.mm.put = MagicMock()

    def test_SourceConsumer_basics(self):
        self.sc = SourceConsumer(self.mm, configurable_gn(1, 0.1))
        self.assertIsInstance(self.sc, StoppableThread)

    def test_SourceConsumer_stops_on_StopIteration(self):
        # Set a source consumer, expect StopIteration
        self.sc = SourceConsumer(self.mm, configurable_gn(10, 0.1))
        self.sc.start()
        time.sleep(1.1)
        # The source should have stopped due to StopIteration:
        self.assertFalse(self.sc.stopped()) # stop() never gets called
        self.assertFalse(self.sc.isAlive())
        # The source should have put 10 integers on the queue:
        self.assertEqual([call(i) for i in xrange(10)], self.mm.put.call_args_list)

    def test_SourceConsumer_stops_on_Full(self):
        def raise_Full_gn():
            if False:
                yield
            else:
                raise Full
        # Generate more values than the queue size:
        self.sc = SourceConsumer(self.mm, raise_Full_gn())
        self.sc.start()
        time.sleep(0.1)
        self.assertFalse(self.sc.stopped()) # stop() never gets called
        self.assertFalse(self.sc.isAlive())

    def test_SourceConsumer_behavior_on_other_exceptions(self):
        def raise_Exception_gn():
            for i in xrange(10): # will never go past 5
                yield float(i)/(5-i)

        self.sc = SourceConsumer(self.mm, raise_Exception_gn())
        self.sc.start()
        time.sleep(0.1)
        self.assertFalse(self.sc.stopped()) # Although the thread is dead, stopped reports incorrect info
        self.assertFalse(self.sc.isAlive())

    def tearDown(self):
        try:
            self.sc.stop()
        except Exception as e:
            pass
        try:
            del self.sc
        except Exception as e:
            pass
        try:
            self.m._source.stop()
        except Exception as e:
            pass
        try:
            self.m.stop()
        except Exception as e:
            pass
        try:
            del self.m
        except Exception as e:
            pass

class TestMachine(unittest.TestCase):
    def setUp(self):
        self.m = Machine()

    def test_Machine_basics(self):
        self.assertIsInstance(self.m, BaseMachine)
        self.assertFalse(self.m.running)

    def test_Machine_running(self):
        pass

    def tearDown(self):
        try:
            self.m.stop()
        except Exception as e:
            pass
        try:
            del self.m
        except Exception as e:
            pass


class TestMachineConsumer(unittest.TestCase):
    def setUp(self):
        pass

    def test_MachineConsumer_basics(self):
        pass



if __name__ == "__main__":
    unittest.main()

        

