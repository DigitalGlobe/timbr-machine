from twisted.internet import reactor

import sys
import argparse
import re
import keyword
import os

from collections import defaultdict
import tables

from twola.datastore.hdf5 import UnstructuredStore
import timbr.serializer as serializer

from txzmq import ZmqEndpoint, ZmqFactory, ZmqSubConnection

from twisted.python import log
from twisted.internet.defer import inlineCallbacks, returnValue, DeferredLock
from twisted.internet.task import cooperate, LoopingCall

from autobahn.twisted.wamp import ApplicationRunner, ApplicationSession
from autobahn.wamp.exception import ApplicationError
from autobahn.wamp.types import RegisterOptions, ComponentConfig
from autobahn.twisted.util import sleep

_capture_runner = None


class CaptureConnection(ZmqSubConnection):
    def __init__(self, factory, endpoint, datastore, key="default", oid_pattern=r'[0-9a-fA-F]+$'):
        self._endpoint = endpoint
        self._key = key
        self._datastore = datastore
        self._oid_pattern = oid_pattern
        ZmqSubConnection.__init__(self, factory, ZmqEndpoint('connect', endpoint))
        self.subscribe("")

    def gotMessage(self, message, header):
        oid = re.findall(self._oid_pattern, header)[0]
        self._datastore.append(self._key, "%s%s" % (serializer.dumps(header), message), oid)


class WampCaptureComponent(ApplicationSession):
    def __init__(self, config=ComponentConfig(realm=u"twola"), basename="/twola-data/data/.capture"):
        ApplicationSession.__init__(self, config=config)
        self._subscriptions = {}
        self._basename = basename
        self._datastore = UnstructuredStore(self._basename)
        self._iterlocks = defaultdict(DeferredLock)
        self._factory = ZmqFactory()
        self._auto_flusher = LoopingCall(self._flush)
        self._auto_flusher.start(10.0) # Should make this interval value configurable

    def _flush(self):
        try:
            self._datastore.flush()
        except Exception, e:
            log.msg("Exception caught in _auto_flush: %s" % str(e))

    @inlineCallbacks
    def onJoin(self, details):
        log.msg("[WampCaptureComponent] onJoin()")

        def subscriptions():
            return self._subscriptions.keys()

        log.msg("[WampCaptureComponent] Registering Procedure: io.timbr.twola.captures.subscriptions")
        yield self.register(subscriptions, 'io.timbr.twola.captures.subscriptions')

        def subscribe(endpoint, key, structure_level=0):
            assert re.match("[_A-Za-z][_a-zA-Z0-9]*", key)
            assert not keyword.iskeyword(key)

            if key in self._subscriptions:
                return False
            else:
                self._datastore.create(key)
                self._subscriptions[key] = -(self._factory, endpoint, key, self._datastore)
                return True

        log.msg("[WampCaptureComponent] Registering Procedure: io.timbr.twola.captures.subscribe")
        yield self.register(subscribe, 'io.timbr.twola.captures.subscribe')

        def unsubscribe(key):
            if(key in self._subscriptions):
                self._subscriptions[key].shutdown()
                self._datastore.checkpoint(key)
                del self._subscriptions[key]

        log.msg("[WampCaptureComponent] Registering Procedure: io.timbr.twola.captures.unsubscribe")
        yield self.register(unsubscribe, 'io.timbr.twola.captures.unsubscribe')

        def flag_endpoint(endpoint):
            dirty_keys = [key for key in self._subscriptions if self._subscriptions[key]._endpoint == endpoint]
            for key in dirty_keys:
                self._datastore.checkpoint(key)
            if(len(dirty_keys) > 0):
                return True
            else:
                return False

        log.msg("[WampCaptureComponent] Registering Procedure: io.timbr.twola.captures.flag_endpoint")
        yield self.register(flag_endpoint, 'io.timbr.twola.captures.flag_endpoint')

        @inlineCallbacks
        def captures():
            output = []
            for key in self._datastore.captures:
                rec = {"key": key, "active": key in self._subscriptions}
                rec["segments"] = []
                for segment in self._datastore.segments(key):
                    preview_item = yield preview(key, segment=segment)
                    rec["segments"].append({"name": segment, "rows": self._datastore.nrows(key, segment),
                                    "preview": preview_item})
                output.append(rec)
            returnValue(output)

        log.msg("[WampCaptureComponent] Registering Procedure: io.timbr.twola.captures.captures")
        yield self.register(captures, 'io.timbr.twola.captures.captures')

        @inlineCallbacks
        def preview(key, count=5, segment='current'):
            @inlineCallbacks
            def critical():
                preview_items = yield self._datastore.fetch(key, segment, n=count)
                returnValue([serializer.wamp_safe_loads(item.tostring()) for item in preview_items])

            result = yield self._iterlocks[key].run(critical)
            returnValue(result)

        log.msg("[WampCaptureComponent] Registering Procedure: io.timbr.twola.captures.preview")
        yield self.register(preview, 'io.timbr.twola.captures.preview')

        @inlineCallbacks
        def counter(key, details=None):
            current_rowcount = -1
            while key in self._subscriptions:
                current_segment = self._datastore.segments(key)[-1]
                rowcount = self._datastore.nrows(key, current_segment)
                if rowcount > current_rowcount:
                    current_rowcount = yield rowcount
                    details.progress({"name": current_segment, "rows": current_rowcount})
                yield sleep(0.5)
            returnValue(None)

        log.msg("[WampCaptureComponent] Registering Procedure: io.timbr.twola.captures.counter")
        yield self.register(counter, 'io.timbr.twola.captures.counter', RegisterOptions(details_arg='details'))

        @inlineCallbacks
        def stream(key, details=None):
            @inlineCallbacks
            def critical():
                for rec in self._datastore.stream(key):
                    yield details.progress(serializer.wamp_safe_loads(rec.tostring()))
                returnValue(None)

            yield self._iterlocks[key].run(cooperate(critical()).whenDone())
            returnValue(None)

        log.msg("[WampCaptureComponent] Registering Procedure: io.timbr.twola.captures.stream")
        yield self.register(stream, 'io.timbr.twola.captures.stream', RegisterOptions(details_arg='details'))

        @inlineCallbacks
        def raw_stream(key, details=None):
            @inlineCallbacks
            def critical():
                for rec in self._datastore.stream(key):
                    yield details.progress(rec.tostring() + '\n')
                returnValue(None)

            yield self._iterlocks[key].run(cooperate(critical()).whenDone())
            returnValue(None)

        log.msg("[WampCaptureComponent] Registering Procedure: io.timbr.twola.captures.raw_stream")
        yield self.register(raw_stream, 'io.timbr.twola.captures.raw_stream', RegisterOptions(details_arg='details'))

        @inlineCallbacks
        def snapshot(key, snapfile, segments, details=None):
            def generate(raw, key, segment):
                for row in self._datastore.stream(key, segment):
                    yield raw.append(row)

            @inlineCallbacks
            def critical():
                self._datastore.flush(key)
                snap = tables.open_file(snapfile, "w")
                raw = snap.create_vlarray(snap.root, "raw", atom=tables.UInt8Atom(shape=()),
                                      filters=tables.Filters(complevel=0))
                snap.create_group(snap.root, "tables")
                for segment in segments:
                    yield cooperate(generate(raw, key, segment)).whenDone()
                    details.progress({"capture_key": key, "status": True})
                    raw.flush()
                snap.flush()
                snap.close()

            yield self._iterlocks[key].run(critical)


        log.msg("[WampCaptureComponent] Registering Procedure: io.timbr.twola.captures.snapshot")
        yield self.register(snapshot, 'io.timbr.twola.captures.snapshot', RegisterOptions(details_arg='details'))

    def onLeave(self, details):
        self._flush()
        log.msg("[WampCaptureComponent] onLeave()")
        log.msg("details: %s" % str(details))
        reactor.callLater(0.25, _capture_runner.run, WampCaptureComponent, start_reactor=False)

    def onDisconnect(self):
        log.msg("[WampCaptureComponent] onDisconnect")



def main():
    global _capture_runner
    log.startLogging(sys.stdout)

    parser = argparse.ArgumentParser()
    parser.add_argument("-b", "--bind", default="ipc:///tmp/twola-captd")
    parser.add_argument("--debug", action="store_true", help="Enable debug output.")
    parser.add_argument("-r", "--realm", default="twola", help="Router realm")
    parser.add_argument("-c", "--connect", default=u"127.0.0.1", help="Router host address")
    parser.add_argument("-p", "--port", default=9000, type=int, help="Router port")
    args = parser.parse_args()

    _capture_runner = ApplicationRunner(url=u"ws://{}:{}".format(args.connect, args.port),
                                        realm=unicode(args.realm),
                                        debug=args.debug,
                                        debug_wamp=args.debug,
                                        debug_app=args.debug)

    log.msg("Connecting to router: ws://%s:%i" % (args.connect, args.port))
    log.msg("  Project Realm: %s" % (args.realm))

    _capture_runner.run(WampCaptureComponent, start_reactor=False)

    reactor.run()