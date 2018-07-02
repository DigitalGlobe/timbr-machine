import tables
import numpy as np
import re
from collections import defaultdict

import logging
_logger = logging.getLogger('timbr.datastore.hdf5')

from timbr.datastore.unstructured import AbstractUnstructuredStore


class UnstructuredStore(AbstractUnstructuredStore):
    def __init__(self, basename="/machine/data/.capture", ext=".h5", project_name="Unknown", store={}):
        super(UnstructuredStore, self).__init__()
        self._fileh = tables.open_file("".join([basename, ext]), mode="a", title=project_name)
        self._groups = {group._v_name: group for group in self._fileh.root._f_iter_nodes("Group")}
        self._segment_limits = defaultdict(None, {group._v_name: group._v_attrs['_twola_n_segments']
                                                  for group in self._fileh.root._f_iter_nodes("Group")
                                                  if '_twola_n_segments' in group._v_attrs})

    @property
    def captures(self):
        return [key for key in self._groups]

    def create(self, key, n=5):
        if key not in self._groups:
            self._groups[key] = self._fileh.create_group(self._fileh.root, key, title=key)
        if "current" not in self._groups[key]:
            # NOTE: Creating as a UInt8Atom because of issues with implicit byte conversion using
            # VLStringAtom (that I don't understand).  Effect should be the same
            self._fileh.create_vlarray(self._groups[key], "current", atom=tables.UInt8Atom(shape=()),
                                       filters=tables.Filters(complevel=0))
        self._segment_limits[key] = n
        self._groups[key]._v_attrs['_twola_n_segments'] = n

        self._fileh.flush()

    def append(self, key, data, oid=None):
        # Explicit conversion of string into bytes
        self._groups[key].current.append(np.fromstring(data, dtype="uint8"))

    def delete(self, key, segment):
        segment = self._groups[key].__getattr__(segment)
        segment._f_remove()

    def segments(self, key):
        try:
            return [segment.name for segment in self._groups[key]._f_iter_nodes("VLArray")]
        except KeyError as ke:
            return None

    def nrows(self, key, segment):
        segment = self._groups[key].__getattr__(segment)
        return segment.nrows

    def rename(self, key, new_name):
        self._groups[key].current.rename(new_name)

    def fetch(self, key, segment, n=5):
        return [e for e in self._groups[key].__getattr__(segment)[-n:]]

    def stream(self, key, segment):
        for rec in self._groups[key].__getattr__(segment):
            yield rec

    def flush(self, key=None):
        if key is None:
            for capture in self.captures:
                self.flush(capture)
        else:
            try:
                self._groups[key].current.flush()
            except KeyError as ke:
                # ignore attempts to flush missing captures
                pass

    def __getitem__(self, key):
        return self._groups[key]

    def __del__(self):
        self._fileh.flush()
        self._fileh.close()
