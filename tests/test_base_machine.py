import unittest

from timbr.machine.base_machine import BaseMachine, json_serialize

try:
    from Queue import Empty, Full, Queue # Python 2
except ImportError:
    from queue import Empty, Full, Queue # Python 3

from dask.threaded import get
from dask.multiprocessing import RemoteException
import functools
from timbr.machine.util import identity, wrap_transform, json_serializable_exception
from bson.objectid import ObjectId


def fn_a(x):
    return x + 5

def fn_b(x, y):
    return x - y

class TestBaseMachine(unittest.TestCase):
    def setUp(self):
        self.bm = BaseMachine()

    def test_wrap_function(self):
        g = wrap_transform(fn_b)
        self.assertEqual(g(7, 5, 8, 9, 10, 11, "q"), fn_b(7, 5))

    def test_BaseMachine_init(self):
        self.assertIsInstance(self.bm.q, Queue)

        status = {"last_oid": None, "processed": 0, "errored": 0, "queue_size": self.bm.q.qsize()}
        self.assertDictEqual(self.bm._status, status)

        self.assertTrue(self.bm._dirty)
        self.assertIs(self.bm._getter.func, get)
        self.assertDictEqual(self.bm._getter.keywords, {"num_workers": 1})
        self.assertIs(self.bm.serialize_fn, json_serialize)

        RD = {"oid_s": (str, "oid"), "in_s": (self.bm.serialize_fn, "in")}
        D = {"f{}_s".format(i): (self.bm.serialize_fn, "f{}".format(i)) for i in range(self.bm.stages)}
        RD.update(D)
        self.assertDictEqual(self.bm.REFERENCE_DASK, RD)

    def test_BaseMachine_basics(self):
        # Test __setitem__, __getitem__ and some attrs on the function
        self.bm[0] = fn_a
        f = self.bm[0]
        self.assertEqual(f(7, 5, 8, 9, 10, 11, "q"), fn_a(7))
        self.assertEqual(f.func_name, "wrapped")

        # Test __len__
        self.assertEqual(len(self.bm), self.bm.stages)

        # Test __delitem__
        del self.bm[0]
        with self.assertRaises(KeyError):
            f = self.bm[0]
        self.assertNotIn("f0", self.bm.tbl)

        # Test put
        self.bm.put(5)
        self.assertEqual(self.bm.q.qsize(), 1)

    def test_BaseMachine_data_processing(self):
        self.bm[0] = fn_a
        self.bm[1] = fn_b
        # Test __call__
        data = 1.0
        res = self.bm(data)
        self.assertIsInstance(res, tuple)
        oid = res[0]
        self.assertIsInstance(oid, ObjectId)
        _r1 = fn_a(data)
        _r2 = fn_b(_r1, data)
        expected = [oid, data, _r1, _r2] + [wrap_transform(identity)(_r2)] * (self.bm.stages - 2)
        self.assertEqual(res, tuple(expected))

        res_s = self.bm(data, include_serialized=True)
        oid = res_s[0]
        expected = [oid, data, _r1, _r2] + [wrap_transform(identity)(_r2)] * (self.bm.stages - 2)
        serialized = [json_serialize(r) for r in expected[1:]]
        expected.extend([str(oid)])
        expected.extend(serialized)
        self.assertEqual(res_s, tuple(expected))

        with self.assertRaises(RemoteException):
            self.bm("incorrect data type")

        # Test put, get
        self.bm.put(data)
        res = self.bm.get()
        self.assertEqual(res[1:], tuple(serialized))

        with self.assertRaises(Empty):
            self.bm.get()



if __name__ == "__main__":
    unittest.main()
