import types
import warnings
from itertools import izip
import threading
import os
import re
import time

import logging
_logger = logging.getLogger("timbr.datastore.snapshot")

import numpy as np
import tables
import simplejson as json
import jsonpath_rw as jsonpath

from timbr.machine import serializer
from timbr.machine.util import isidentifier, camelcase_to_underscored
from timbr.snapshot.exception import IncompleteSyncError


class NotSupportedException(NotImplementedError):
    pass


# StructuringFunction Specification Format:
# spec = [{"input_data_type": "...",
#         "input_default_val": "...",
#         "name": "...",
#         "path": "..."}, ... ]

CAST_MAP = {'bool': bool, 'int': int, 'float': float, 'str': unicode}
VALID_DEFAULT_TYPES = (bool, int, long, float, str, unicode, types.NoneType)


class StructuringFunction(object):
    def __init__(self, fn=lambda x: x, spec=None):
        self._fn = fn
        self._spec = spec

    def __call__(self, rec):
        return self._fn(rec)

    @property
    def spec(self):
        if self._spec is not None:
            return self._spec
        else:
            raise NotImplementedError

    @classmethod
    def from_spec(cls, spec):
        return cls(cls._structuring_function(spec), spec)

    @staticmethod
    def _structuring_function(colspecs):
        def _gen_castfn(spec):
            _validate(spec)
            castfn = CAST_MAP.get(spec['input_data_type'], lambda x: x)
            return castfn

        def _validate(spec):
            if spec['input_data_type'] not in CAST_MAP:
                warnings.warn("Unrecognized input_data_type in specification ", UserWarning)
            if not isinstance(spec['input_default_val'], VALID_DEFAULT_TYPES):
                warnings.warn("Unrecognized input_default_val data type in specification", UserWarning)

        def _colspec_fn(spec):
            jsonpath_expr = jsonpath.parse(spec['path'])
            castfn = _gen_castfn(spec)
            def fnc(rec):
                try:
                    match = jsonpath_expr.find(rec)[0].value
                    return castfn(match)
                except (KeyError, IndexError, TypeError, ValueError), e:
                    # NOTE: we return the default value on nearly any exception.  need to be careful
                    # about data corruption resulting from this.
                    return castfn(spec['input_default_val'])
            return fnc

        # NOTE: The UI is building specs with camelcased key names, converting them to underscored here.
        _colspecs = [{camelcase_to_underscored(k): v for k,v in spec.iteritems()} for spec in colspecs]
        _tblspec = {spec['name']: _colspec_fn(spec) for spec in _colspecs}

        def spec_function(rec):
            return {k: v(rec) for k, v in _tblspec.iteritems()}

        return spec_function


class WrappedRawArray(object):
    def __init__(self, raw, input_fn=serializer.loads):
        self._raw = raw
        self._input_fn = input_fn

    def __getitem__(self, spec):
        if isinstance(spec, (int, long)):
            return self._input_fn(self._raw[spec].tostring())
        else:
            return list(self.__iter__(spec))

    def __iter__(self, spec=slice(None)):
        if isinstance(spec, slice):
            for rec in self._raw.iterrows(spec.start, spec.stop, spec.step):
                yield self._input_fn(rec.tostring())
        else:
            for rec in self._raw[spec]:
                yield self._input_fn(rec.tostring())

    def __setitem__(self, key, value):
        raise NotSupportedException("For your protection, overwriting raw data in snapshots is not supported.")

    def __len__(self):
        return len(self._raw)


class Snapshot(WrappedRawArray):
    def __init__(self, filename):
        self._filename = filename
        self._fileh = tables.open_file(filename, mode='r')
        try:
            super(Snapshot, self).__init__(self._fileh.root.raw)
        except tables.NoSuchNodeError, ne:
            self._fileh.close()
            raise IOError("Snapshot corrupted or not ready yet: %s" % str(ne))

    @property
    def raw(self):
        return self._raw # from superclass

    def close(self):
        self._fileh.close()

    @property
    def _shadow_file(self):
        head, tail = os.path.split(self._filename)
        return os.path.join(head, ".%i-shdw~%s" % (os.getpid(), tail))

    @property
    def _all_shadow_files(self):
        head, tail = os.path.split(self._filename)
        pattern = re.compile("\.\d+-shdw~%s" % tail)
        return [os.path.join(head, filename) for filename in os.listdir(head) if pattern.match(filename)]

    @property
    def tables(self):
        try:
            return self._fileh.root.tables._v_leaves.keys()
        except tables.NoSuchNodeError, ne:
            warnings.warn("'tables' group doesn't exist in '%s'.  No tables have been created yet." % self._filename)
            return []

    @property
    def tbl(self):
        return {k: WrappedRawArray(v) for k,v in self._fileh.root.tables._v_leaves.iteritems()}

    @property
    def pending_tables(self):
        warnings.warn("This can be a relatively intensive method, use sparingly")
        tbls = []
        for shadowfile in self._all_shadow_files:
            try:
                shadow = tables.open_file(shadowfile, "r")
                tbls.extend(shadow.root.tables._v_leaves.keys())
            except tables.NoSuchNodeError, ne:
                shadow.close()
            except (IOError, tables.HDF5ExtError), e:
                warnings.warn("Shadow file '%s' doesn't exists or is unreadable.  No pending tables exist." % shadowfile)
            finally:
                try:
                    shadow.close()
                except:
                    pass
        return tbls

    def build_table(self, name, spec, style='raw', sync=False, progress=lambda x: x, progress_interval=1.0):
        if style not in ['raw']:
            raise NotImplementedError("Building '%s' tables are not supported yet." % style)

        try:
            shadow = tables.open_file(self._shadow_file, "a")
            shadow.flush()
        except (tables.HDF5ExtError, ValueError), e:
            _logger.info("Unable to open shadow file in read-write mode.  Giving up.")
            return False

        try:
            if "raw" not in shadow.root:
                self._fileh.root.raw._f_copy(shadow.root, "raw")
            if "tables" not in shadow.root:
                shadow.create_group(shadow.root, "tables")

            assert isidentifier(name), "Table name should be a valid python identifier"
            assert name not in shadow.root.tables, "Table name should be unique"

            if style == 'raw':
                table = shadow.create_vlarray(shadow.root.tables, name,
                                                   atom=tables.UInt8Atom(shape=()),
                                                   filters=tables.Filters(complevel=0))
                tabularize = StructuringFunction.from_spec(spec)
                table.attrs.spec = json.dumps(tabularize.spec)

                reference_time = time.time()
                for idx, (oid, rec) in enumerate(self):
                    try:
                        payload = serializer.dumps(tabularize(rec))
                        table.append(np.fromstring(payload, dtype="uint8"))
                        if(time.time() - reference_time > progress_interval):
                            progress((idx, len(self)))
                    except:
                        _logger.error("Error tabularizing record (probably) at row %i." % idx)
                        raise
            elif style == 'dense':
                raise NotImplementedError("Building dense tables is not yet supported.")
                # TODO build dense table structure from spec
                # TODO build spec mapping function
                # TODO create dense table leaf node
                # TODO process raw -> dense via map
            else:
                raise NotImplementedError("%s is not a known table style." % style)
        except tables.HDF5ExtError, e:
            # Something important failed.  Try and clean up.
            if "raw" in shadow.root:
                shadow.remove_node(shadow.root, "raw")
            if "tables" in shadow.root:
                if name in shadow.root.tables:
                    shadow.remove_node(shadow.root.tables, name)
        finally:
            # NOTE: no matter what, if we got to this block then we need to close things afterwards
            shadow.flush()
            shadow.close()

        if sync:
            self.sync()

        return True

    def reset(self, mode="r"):
        valid_modes = ["r", "a"]
        assert mode in valid_modes
        assert isinstance(self._fileh, tables.File)

        if self._fileh.isopen:
            if self._fileh.mode == mode:
                return
            else:
                self._fileh.close()

        try:
            self._fileh = tables.open_file(self._filename, mode)
            self._raw = self._fileh.root.raw
        except (ValueError, tables.HDF5ExtError), e:
            # If we couldn't open file in write mode, try the other.  Either way raise exception
            if mode == "a":
                try:
                    self.reset()
                except IOError, ioe:
                    warnings.warn("Unable to recover from inaccessible snapshot file.")
            raise IOError("Unable to open snapshot file '%s' in mode '%s': \n%s" % (self._filename, mode, str(e)))

    def sync_shadowfile(self, shadowfile):
    # 1) open shadow file read only
    #    - if we cant, list it as pending
    #    - if there isn't a tables group, list it as pending
        try:
            shadow = tables.open_file(shadowfile, "r")
            num_tables = len(shadow.root.tables._v_leaves)
            num_copied = 0
    # 2) iterate/copy tables
    #    - if we can't copy the table for whatever reason, flush main snapshot and
    #      clean up
            for table in shadow.root.tables:
                try:
                    table._f_copy(self._fileh.root.tables, table._v_name)
                    num_copied = num_copied + 1
                except tables.NodeError, ne:
                    warnings.warn("A table named '%s' already exists in snapshot file." % table._v_name)
            os.remove(shadowfile)
            return (num_tables, num_copied)
        except (ValueError, tables.HDF5ExtError), e:
            # NOTE: this file is not our responsibility yet.  Something else must be working on it
            return (None, None) # -> means "pending"
        except tables.NoSuchNodeError:
            warnings.warn("Shadow file '%s' does not have any tables.  Skipping. " % shadowfile)
            return (0, 0)
        finally:
            self._fileh.flush()
            try:
                shadow.close() # Interestingly file can be closed after os.remove is called
            except:
                pass # unconditionally protecting close in case open_file failed

    def sync(self):
        if len(self.pending_tables) == 0:
            return False # no need to do anything
        # 1) Close file and reopen it in rw mode ('a')
        #    - reset file handle, raw pointer, raise exception if we cant open the file
        self.reset("a")

        # 2) Create the tables group if it doesn't already exist
        if "tables" not in self._fileh.root:
            self._fileh.create_group(self._fileh.root, "tables")

        # 3) Try and sync each shadow file
        #    - record failures as having pending tables
        sync_statuses = [self.sync_shadowfile(shadowfile) for shadowfile in self._all_shadow_files]

        # 4) Reset file handle, raw pointer
        self.reset()

        # 5) compute a bunch of diagnostic data
        has_pending_tables = any([(None, None) == status for status in sync_statuses])
        completed = not has_pending_tables
        did_work = any([(0, 0) != status for status in sync_statuses])
        errored = any([status[0] != status[1] for status in sync_statuses])

        # 6) return or raise things based on diagnostic data
        if has_pending_tables:
            raise IncompleteSyncError("Incomplete Sync! (%s: %s)" % (self._filename, str(self._all_shadow_files)))

        return completed and did_work