from dask.callbacks import Callback
from timeit import default_timer


class MachineProfiler(Callback):
    """A profiler for dask execution at the task level.

    If you use the profiler globally you will need to clear out old results
    manually.
    >>> prof.clear()
    """
    def __init__(self):
        self._dsk = {}
        self._successful = []
        self._current = None
        self._errored = None
        self._cache = None

    def __enter__(self):
        self.clear()
        return super(MachineProfiler, self).__enter__()

    def _start(self, dsk):
        self._dsk.update(dsk)

    def _pretask(self, key, dsk, state):
        # state is a dict
        self._current = key

    def _posttask(self, key, value, dsk, state, id):
        self._successful.append(key)

    def _finish(self, dsk, state, failed):
        if failed:
            self._errored = self._current
            self._cache = state["cache"].copy()
            
    def clear(self):
        """Clear out old results from profiler"""
        del self._successful[:]
        self._current = None
        self._errored = None
        self._cache = None
        self._dsk = {}