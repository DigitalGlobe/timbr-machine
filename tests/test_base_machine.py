import unittest

from timbr.machine.base_machine import BaseMachine, json_serialize

try:
    from Queue import Empty, Full, Queue # Python 2
except ImportError:
    from queue import Empty, Full, Queue # Python 3

from dask.threaded import get
import functools
from timbr.machine.util import identity, wrap_transform, json_serializable_exception
from timbr.machine.profiler import MachineProfiler


class TestBaseMachine(unittest.TestCase):
	def setUp(self):
		self.bm = BaseMachine()

	def test_BaseMachine_init(self):
		self.assertIsInstance(self.bm.q, Queue)

		status = {"last_oid": None, "processed": 0, "errored": 0, "queue_size": self.bm.q.qsize()}
		self.assertDictEqual(self.bm._status, status)

		self.assertTrue(self.bm._dirty)
		self.assertIs(self.bm._getter.func, get)
		self.assertDictEqual(self.bm._getter.keywords, {"num_workers": 1})
		self.assertIsInstance(self.bm._profiler, MachineProfiler)
		self.assertIs(self.bm.serialize_fn, json_serialize)

		RD = {"oid_s": (str, "oid"), "in_s": (self.bm.serialize_fn, "in")}
		D = {"f{}_s".format(i): (self.bm.serialize_fn, "f{}".format(i)) for i in xrange(self.bm.stages)}
		RD.update(D)
		self.assertDictEqual(self.bm.REFERENCE_DASK, RD)

	def test_BaseMachine_basics(self):
		# Test __getitem__, __missing__ behavior
		for i in xrange(self.bm.stages):
			with self.assertRaises(KeyError):
				f = self.bm[i]

		# Test __setitem__, __getitem__ and some attrs on the function
		def a_user_defined_function(x):
			return x + 5
		self.bm[0] = a_user_defined_function
		f = self.bm[0]
		self.assertEqual(f.func_name, "wrapped")

		self.assertEqual(len(self.bm), self.bm.stages)








if __name__ == "__main__":
	unittest.main()







