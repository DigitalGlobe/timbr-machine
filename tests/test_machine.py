import unittest
try:
    from mock import MagicMock, call
except ImportError:
    from unittest.mock import MagicMock, call

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
import random, time
import contextlib
import warnings

def configurable_gn(s):
    for i in xrange(s):
        yield i

class MockMachine(object):
    def put(self, x):
        pass

class TestSourceConsumer(unittest.TestCase):
    def setUp(self):
        self.mm = MockMachine()
        self.sc = SourceConsumer(self.mm, configurable_gn(10))

    def test_SourceConsumer_basics(self):
        self.assertIsInstance(self.sc, StoppableThread)

    def test_SourceConsumer_calls_put_with_generated_values(self):
        self.mm.put = MagicMock()
        self.sc.start()
        self.sc.join()
        self.assertEqual([call(i) for i in xrange(10)], self.mm.put.call_args_list)

    def test_SourceConsumer_stops_on_StopIteration(self):
        self.mm.put = MagicMock()
        self.sc.start()
        self.sc.join()
        self.assertFalse(self.sc.stopped())
        self.assertFalse(self.sc.isAlive())

    def test_SourceConsumer_stops_on_Full(self):
        self.mm.put = MagicMock(side_effect = Full)
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
        except (AttributeError, NameError):
            pass

class TestException(Exception):
    def __init__(self, msg):
        self.msg = msg

def raise_an_exception():
    raise TestException("Deal with it")

class TestMachine(unittest.TestCase):
    @contextlib.contextmanager
    def assertWarns(self, warning, *args, **kwargs):
        """A test that checks if a specified warning was raised"""
        original_filters = warnings.filters[:]
        warnings.simplefilter('error')
        if len(args) == 0 and len(kwargs) == 0:
            with self.assertRaises(warning):
                yield
        else:
            self.assertRaises(warning, *args, **kwargs)
        warnings.filters = original_filters

    def setUp(self):
        self.m = Machine()

    def test_Machine_basics(self):
        self.assertIsInstance(self.m, BaseMachine)
        self.assertFalse(self.m.running)
        self.assertIsInstance(self.m._profiler, MachineProfiler)

    def test_Machine_start_stop(self):
        self.m.start()
        self.assertTrue(self.m.running)
        self.m.stop()
        self.assertFalse(self.m.running)

    def test_Machine_set_source_functionality(self):
        self.m.set_source(configurable_gn(10))
        self.m._source.join()
        self.assertEqual(self.m.status["queue_size"], 10)

    def test_Machine_behavior_on_Empty(self):
        self.m.start()
        time.sleep(0.1)
        self.assertEqual(self.m.status["errored"], 0)

    def test_Machine_modes(self):
        # Test default is False:
        self.assertFalse(self.m.debug)
        self.m[0] = raise_an_exception
        self.m.start()
        self.m.put(10) # No exception raised
        time.sleep(1.0)
        self.assertEqual(self.m.status["errored"], 1)
        self.assertTrue(self.m.running)
        # Test we can't enter debug mode from default:
        with self.assertWarns(UserWarning):
            self.m.enable_debug_mode()
        self.assertFalse(self.m.debug)

        # Test entering debug mode after stop:
        self.m.stop()
        self.m.enable_debug_mode()
        self.m.start()
        self.assertTrue(self.m.debug)
        self.m.put(10) # Will raise error in thread
        time.sleep(1.0)
        self.assertFalse(self.m.running)

    def tearDown(self):
        try:
            self.m.stop()
            del self.m
        except (AttributeError, NameError):
            pass

class TestMachineConsumer(unittest.TestCase):
    def setUp(self):
        pass

    def test_MachineConsumer_basics(self):
        pass


if __name__ == "__main__":
    unittest.main()
