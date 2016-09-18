def _build_table_work_fn(snapfile, name, tblspec):
    from timbr.machine.snapshot import Snapshot
    snapshot = Snapshot(snapfile)
    snapshot.build_table(name, tblspec, style="raw", sync=False)
    snapshot.close()

import multiprocessing as mp
_process_pool = mp.Pool(processes=2, maxtasksperchild=1)

from twisted.internet import reactor, threads

import sys
import warnings
import os.path
import argparse
from collections import defaultdict
import functools
import re

from bson.objectid import ObjectId
import tables
import sh

from timbr.snapshot.exception import IncompleteSyncError
from timbr.machine.snapshot import Snapshot
import timbr.machine.serializer as serializer
import logging
_logger = logging.getLogger("timbr.snapshot")

from watchdog.observers import Observer
from watchdog.events import RegexMatchingEventHandler
from watchdog.events import DirModifiedEvent

from twisted.python import log
from twisted.internet.defer import inlineCallbacks, returnValue, DeferredLock, DeferredQueue, Deferred
from twisted.internet.task import cooperate

from autobahn.twisted.wamp import ApplicationRunner, ApplicationSession
from autobahn.twisted.util import sleep
from autobahn.wamp.exception import ApplicationError
from autobahn.wamp.types import RegisterOptions, ComponentConfig
from autobahn import wamp

from timbr.machine.util import make_wamp_safe

_project_realm = os.environ.get('PROJECT_REALM', "jupyter")
_snapshot_runner = None

class LoggingEventHandler(RegexMatchingEventHandler):
    def __init__(self):
        super(LoggingEventHandler, self).__init__(ignore_regexes=['^.*\.log$'])

    def on_any_event(self, event):
        _logger.debug("Event Received [%s]" % type(event).__name__)

    def on_modified(self, event):
        _logger.debug("  Path Modified [%s]" % event.src_path)

    def on_created(self, event):
        _logger.debug("  Path Created [%s]" % event.src_path)

    def on_deleted(self, event):
        _logger.debug("  Path Deleted [%s]" % event.src_path)

    def on_moved(self, event):
        _logger.debug(" Path Moved [%s] -> [%s]" % (event.src_path, event.dest_path))


def build_snapshot_component(kernel_key):
    class WampSnapshotComponent(ApplicationSession):
        def __init__(self, kernel_key, config=ComponentConfig(realm=unicode(_project_realm)), path="/twola-data/data"):
            ApplicationSession.__init__(self, config=config)
            self._kernel_key = kernel_key
            self.path = path
            self._snapshots = {}
            self._lut = {}
            self._pending_tables = defaultdict(set)

            self._lock = DeferredLock() # global lock
            self._iterlocks = defaultdict(DeferredLock) # local locks
            self._mount_locks = defaultdict(DeferredLock) # mount locks
            self._sync_locks = defaultdict(DeferredLock) # sync locks

            self._automount_queue = DeferredQueue()
            self._automount()
            self.obs = Observer()
            self._start_observer()

        def __del__(self):
            ApplicationSession.__del__(self)
            self.obs.stop()

        def _start_observer(self):
            watch = self.obs.schedule(LoggingEventHandler(), self.path, recursive=False)
            se_handler = SnapshotFileEventHandler(self)
            self.obs.add_handler_for_watch(se_handler, watch)
            self.obs.start()

        @inlineCallbacks
        def onJoin(self, details):
            log.msg("[WampSnapshotComponent] onJoin()")

            log.msg("[WampSnapshotComponent] Registering Procedure: io.timbr.kernel.{}.snapd.list".format(self._kernel_key))
            yield self.register(self.list, 'io.timbr.kernel.{}.snapd.list'.format(self._kernel_key))
            log.msg("[WampSnapshotComponent] Registering Procedure: io.timbr.kernel.{}.snapd.mount".format(self._kernel_key))
            yield self.register(self.mount, 'io.timbr.kernel.{}.snapd.mount'.format(self._kernel_key))
            log.msg("[WampSnapshotComponent] Registering Procedure: io.timbr.kernel.{}.snapd.unmount".format(self._kernel_key))
            yield self.register(self.unmount, 'io.timbr.kernel.{}.snapd.unmount'.format(self._kernel_key))
            log.msg("[WampSnapshotComponent] Registering Procedure: io.timbr.kernel.{}.snapd.fetch".format(self._kernel_key))
            yield self.register(self.fetch, 'io.timbr.kernel.{}.snapd.fetch'.format(self._kernel_key), RegisterOptions(details_arg='details'))
            log.msg("[WampSnapshotComponent] Registering Procedure: io.timbr.kernel.{}.snapd.get".format(self._kernel_key))
            yield self.register(self.get, 'io.timbr.kernel.{}.snapd.get'.format(self._kernel_key))
            log.msg("[WampSnapshotComponent] Registering Procedure: io.timbr.kernel.{}.snapd.sync".format(self._kernel_key))
            yield self.register(self.sync, 'io.timbr.kernel.{}.snapd.sync'.format(self._kernel_key))
            log.msg("[WampSnapshotComponent] Registering Procedure: io.timbr.kernel.{}.snapd.build_table".format(self._kernel_key))
            yield self.register(self.build_table, 'io.timbr.kernel.{}.snapd.build_table'.format(self._kernel_key), RegisterOptions(details_arg='details'))
            log.msg("[WampSnapshotComponent] Registering Procedure: io.timbr.kernel.{}.snapd.mark_as_dirty".format(self._kernel_key))
            yield self.register(self.mark_as_dirty, 'io.timbr.kernel.{}.snapd.mark_as_dirty'.format(self._kernel_key))

        @inlineCallbacks
        def list(self):
            # NOTE: to protect against changing the _snapshots dict while method is running
            @inlineCallbacks
            def critical():
                res = {}
                for k in self._snapshots:
                    res[k] = yield self.get(k)
                returnValue(res)

            result = yield self._lock.run(critical)
            returnValue(result)

        @inlineCallbacks
        def mount(self, path, remount=False):
            # NOTE: to protect against changing the _snapshots, _lut dicts while method is running
            key = self._lut.get(path, str(ObjectId()))
            def critical(key=key):
                if remount and key in self._snapshots:
                    self._snapshots[key].close()
                    self._snapshots[key] = Snapshot(path)
                    self._pending_tables[key] = set(self._snapshots[key].pending_tables)
                elif key not in self._snapshots:
                    try:
                        self._snapshots[key] = Snapshot(path)
                        self._pending_tables[key] = set(self._snapshots[key].pending_tables)
                    except (IOError, ValueError), ne:
                        _logger.warn("Unable to mount snapshot %s: %s" % (path, str(ne)))
                        return None
                    self._lut[path] = key
                else:
                    # NOTE: duplicates pre-lock check functionality
                    warnings.warn("Path %s already mounted with key '%s'" % (path, key))
                return key

            @inlineCallbacks
            def safe_mount(key=key):
                # NOTE: Acquiring this local lock ensures that there will be no concurrency issues with other
                # methods performing operations on the snapshot. Why exactly this is needed would be good to know
                result = yield self._iterlocks[key].run(critical)
                returnValue(result)

            if(remount is False and key in self._snapshots):
                returnValue(key)
            else:
                result = yield self._lock.run(safe_mount)
                returnValue(result)

        @inlineCallbacks
        def unmount(self, key):
            # NOTE: to protect against changing the _snapshots, _lut dicts while method is running
            def critical():
                del self._lut[self._snapshots[key]._filename]
                self._snapshots[key].close()
                del self._snapshots[key]
                try:
                    del self._pending_tables[key]
                except KeyError, ke:
                    pass # no locks have been used for this key
                try:
                    del self._sync_locks[key]
                except KeyError, ke:
                    pass # no locks have been used for this key

            if key in self._snapshots:
                yield self._iterlocks[key].run(critical)
                del self._iterlocks[key]
                returnValue(True)
            else:
                result = yield False
                returnValue(result)

        @inlineCallbacks
        def fetch(self, key, start=None, stop=None, step=1, details=None):
            def critical(ktbl):
                # NOTE: to protect against changing the _snapshots dicts while method is running
                key, tbl = ktbl
                if tbl is None:
                    ref = self._snapshots[key]
                elif tbl not in self._snapshots[key].tables:
                    raise KeyError("Table '%s' not found in snapshot '%s'" % (tbl, key))
                else:
                    ref = self._snapshots[key].tbl[tbl]
                return ref

            def generate(kref):
                # NOTE: to protect against reuse of the underlying pytables iterator by another call
                key, ref = kref
                if start is None and stop is None and step is 1:
                    for row in ref:
                        yield details.progress(make_wamp_safe(row))
                else:
                    for row in ref.__iter__(slice(start,stop,step)):
                        yield details.progress(make_wamp_safe(row))
                returnValue(None)

            tbl = None
            if isinstance(key, (list, tuple)):
                assert len(key) == 2, "When argument 1 is a list or tuple, it must have 2 elements"
                key, tbl = key
            assert key in self._snapshots

            ref = yield self._lock.run(critical, [key, tbl])
            def iterate():
                return cooperate(generate([key, ref])).whenDone()

            yield self._iterlocks[key].run(iterate)
            returnValue(None)

        def get(self, key):
            return {"filename": self._snapshots[key]._filename,
                    "length": len(self._snapshots[key]),
                    "tables": self._snapshots[key].tables,
                    "pending_tables": list(self._pending_tables[key])}


        @inlineCallbacks
        def sync(self, key):
            _logger.debug("Sync called with key: %s" % key)
            @inlineCallbacks
            def critical():
                # NOTE: protecting individual snapshot against modification because we will be opening
                # it rw and modifying it during the sync process.  Therefore iterating or getting info
                # about it is a bad idea while this is running.
                _logger.debug("  Sync iterlock['%s'] acquired." % key)
                if key in self._snapshots:
                    # Execute using deferToThread after all locks have been acquired
                    try:
                        result = yield threads.deferToThread(self._snapshots[key].sync)
                        self._pending_tables[key] = set(self._snapshots[key].pending_tables)
                        returnValue(result)
                    except IncompleteSyncError, e:
                        pass

            result = yield self._lock.run(critical)
            returnValue(result)

        @inlineCallbacks
        def build_table(self, key, name, tblspec, details=None):
            self._pending_tables[key].add(name)
            s =  self.get(key)
            if s is None:
                raise KeyError("Snapshot with key %s doesn't exist or is not mounted." % key)
            snapfile = s["filename"]

            async_result =  _process_pool.apply_async(_build_table_work_fn, [snapfile, name, tblspec])
            yield threads.deferToThread(async_result.get)

            yield self._sync_locks[key].run(self.sync, key)
            returnValue(True)

        @inlineCallbacks
        def mark_as_dirty(self, path):
            if (not self._mount_locks[path].locked and
                path not in self._automount_queue.pending):
                yield self._automount_queue.put(path)

        @inlineCallbacks
        def _automount_one(self, path):
            yield self._mount_locks[path].acquire()
            _logger.debug("Automount processing %s" % path)
            try:
                if path in self._lut:
                    yield self.mount(path, remount=True)
                else:
                    yield self.mount(path)
            except tables.HDF5ExtError, e:
                # empty or (temporarily?) corrupt file
                _logger.debug("Empty or temporarily corrupt file %s: %s" % (path, str(e)))
            except ValueError, ve:
                # the file is already open somewhere else
                _logger.debug("File %s already open somewhere else: %s" % (path, str(ve)))
            self._mount_locks[path].release()
            del self._mount_locks[path]
            returnValue(path)

        @inlineCallbacks
        def _automount(self):
            while True:
                path = yield self._automount_queue.get()
                self._automount_one(path)

        def onLeave(self, details):
            log.msg("[WampSnapshotComponent] onLeave()")
            log.msg("details: %s" % str(details))
            reactor.callLater(0.25, _snapshot_runner.run, WampSnapshotComponent, start_reactor=False)

        def onDisconnect(self):
            log.msg("WampSnapshotComponent] onDisconnect()")


    class SnapshotFileEventHandler(RegexMatchingEventHandler):
        def __init__(self, snapd):
            self.snapd = snapd
            self.reactor = reactor
            super(SnapshotFileEventHandler, self).__init__(['^.*\.h5$'],
                                                           ignore_regexes=['^.*\%s\.(?!\d+-shdw~)[^\%s]+\.h5$' % (os.path.sep, os.path.sep)])
            self._shadow_pattern = re.compile(r'^.*\%s\.(\d+-shdw~)[^\%s]+\.h5$' % (os.path.sep, os.path.sep))
            self._shadow_replacement_pattern = re.compile(r'\%s\.\d+-shdw~([^\%s]+\.h5)$' % (os.path.sep, os.path.sep))

        def on_deleted(self, event):
            if event.src_path in self.snapd._lut:
                self.reactor.callInThread(self.snapd.unmount(self.snapd._lut[event.src_path]))
            elif self._shadow_pattern.match(event.src_path):
                dirty_path = re.sub(self._shadow_replacement_pattern, r'%s\1' % os.path.sep, event.src_path)
                # NOTE: since we sync in-process, we don't need to act on shadow file deletions

        def on_created(self, event):
            _logger.debug("on_created called with src_path: %s" % event.src_path)
            if not self._shadow_pattern.match(event.src_path):
                # NOTE: this indicates that a snapshot has started
                self.on_modified(event)

        def on_modified(self, event):
            if isinstance(event, DirModifiedEvent):
                return
            if not self._shadow_pattern.match(event.src_path):
                # NOTE: indicates that data was written to the snapshot file (not the shadow file)
                # This is needed so that snapshots will get automounted.
                self.reactor.callInThread(self.snapd.mark_as_dirty, event.src_path)

        def on_moved(self, event):
            # NOTE: doesn't use the automount queue (but also is a rare or nonexistent event)
            if event.src_path in self.snapd._lut:
                self.reactor.callInThread(self.snapd.unmount(self.snapd._lut[event.src_path]))
            self.reactor.callInThread(self.snapd.mount, event.dest_path)

        def on_any_event(self, event):
            filename = os.path.split(event.src_path)[-1]
            _logger.debug("Detected change in file: %s" % filename)



def main():
    global _project_realm, _snapshot_runner

    log.startLogging(open("/machine/log/snapd.log", "w"))

    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true", help="Enable debug output.")
    parser.add_argument("--wamp-realm", default=u"jupyter", help='Router realm')
    parser.add_argument("--wamp-url", default=u"wss://juno.timbr.io/wamp/route", help="WAMP Websocket URL")
    parser.add_argument("--token", type=unicode, help="OAuth token to connect to router")
    parser.add_argument("--session-key", help="The kernel key that you want to capture from")
    args = parser.parse_args()


    _capture_runner = ApplicationRunner(url=unicode(args.wamp_url), realm=unicode(args.wamp_realm),
                                        headers={"Authorization": "Bearer {}".format(args.token),
                                                    "X-Kernel-ID": args.session_key})


    log.msg("Connecting to router: %s" % args.wamp_url)
    log.msg("  Project Realm: %s" % (args.wamp_realm))

    _capture_runner.run(build_capture_component(args.session_key), start_reactor=False)

    reactor.run()

