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
import random


def configurable_gn(s):
    for i in xrange(s):
        yield i

class MockMachine(object):
    def put(self, x):
        pass

class TestSourceConsumer(unittest.TestCase):
    def setUp(self):
        self.mm = MockMachine()

    def test_SourceConsumer_basics(self):
        self.sc = SourceConsumer(self.mm, configurable_gn(10))
        self.assertIsInstance(self.sc, StoppableThread)

    def test_SourceConsumer_calls_put_with_generated_values(self):
        self.mm.put = MagicMock()
        self.sc = SourceConsumer(self.mm, configurable_gn(10))
        self.sc.start()
        self.sc.join()
        self.assertEqual([call(i) for i in xrange(10)], self.mm.put.call_args_list)

    def test_SourceConsumer_stops_on_StopIteration(self):
        self.mm.put = MagicMock()
        self.sc = SourceConsumer(self.mm, configurable_gn(10))
        self.sc.start()
        self.sc.join()
        self.assertFalse(self.sc.stopped()) 
        self.assertFalse(self.sc.isAlive())

    def test_SourceConsumer_stops_on_Full(self):
        self.mm.put = MagicMock(side_effect = Full)
        self.sc = SourceConsumer(self.mm, configurable_gn(10))
        self.sc.start()
        self.sc.join()
        self.assertFalse(self.sc.stopped()) # stop() never gets called
        self.assertFalse(self.sc.isAlive())

    def test_SourceConsumer_behavior_on_other_exceptions(self):
        def raise_Exception_gn():
            for i in xrange(10): # will never go past 5
                yield float(i)/(5-i)
        self.sc = SourceConsumer(self.mm, raise_Exception_gn())
        self.sc.start()
        self.sc.join()
        self.assertFalse(self.sc.stopped()) # Although the thread is dead, stopped reports incorrect info
        self.assertFalse(self.sc.isAlive())

    def tearDown(self):
        try:
            self.sc.stop()
            del self.sc
        except NameError as ne:
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

        

