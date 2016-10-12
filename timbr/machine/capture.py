from twisted.internet import reactor

import sys
import argparse
import re
import keyword
import os

from collections import defaultdict
import tables

from txzmq import ZmqEndpoint, ZmqFactory, ZmqSubConnection

from twisted.python import log
from twisted.internet.defer import inlineCallbacks, returnValue, DeferredLock
from twisted.internet.task import cooperate, LoopingCall

from autobahn.twisted.wamp import ApplicationRunner, ApplicationSession
from autobahn.wamp.exception import ApplicationError
from autobahn.wamp.types import RegisterOptions, ComponentConfig
from autobahn.twisted.util import sleep

from timbr.datastore.hdf5 import UnstructuredStore

from timbr.machine import serializer

import json

_capture_runner = None

def _map_message(message):
    d = {}
    for i, msg in enumerate(message):
        if i == 0:
            d["source"] = msg
        else:
            d["f{}".format(i - 1)] = msg
    return d

class CaptureConnection(ZmqSubConnection):
    def __init__(self, factory, endpoint, datastore, subscriptions, oid_pattern=r'[0-9a-fA-F]+$'):
        self._endpoint = endpoint
        self._datastore = datastore
        self._subscriptions = subscriptions
        self._oid_pattern = oid_pattern
        ZmqSubConnection.__init__(self, factory, ZmqEndpoint('connect', endpoint))
        self.subscribe("")

    def gotMessage(self, message, header):
        self._capture(message, header)

    def _capturing(self):
        return any(self._subscriptions.values())

    def _capture(self, msg, hdr):
        if self._capturing():
            oid = re.findall(self._oid_pattern, hdr)[0]
            log.msg("incoming message = {}".format(msg))
            mapped = _map_message(serializer.loads(msg))
            log.msg(json.dumps(mapped))
            for key in self._subscriptions:
                if self._subscriptions[key]:
                    value = mapped.get(key)
                    log.msg(json.dumps(value))
                else:
                    log.msg("Value=None")
                    value = None
                
                payload = "%s%s" % (serializer.dumps(hdr), value)
                log.msg("key={}, payload={}, oid={}".format(key, payload, oid))
                self._datastore.append(key, payload, oid)

def build_capture_component(kernel_key):
    class WampCaptureComponent(ApplicationSession):
        def __init__(self, kernel_key, config=ComponentConfig(realm=u"jupyter"), basename="machine/data/.capture", 
                        base_endpoint="ipc:///tmp/timbr-machine/", tracks=8):
            ApplicationSession.__init__(self, config=config)
            self._kernel_key = kernel_key
            self._subscriptions = {}
            self._basename = basename
            self._datastore = UnstructuredStore(self._basename)
            self._iterlocks = defaultdict(DeferredLock)
            self._auto_flusher = LoopingCall(self._flush)
            self._auto_flusher.start(10.0) # Should make this interval value configurable
            self._configure(tracks)
            self._factory = ZmqFactory()
            self._conn = CaptureConnection(self._factory, os.path.join(base_endpoint, kernel_key), self._datastore, self._subscriptions)

        def _configure(self, tracks):
            if len(self._datastore.captures) > 0:
                self._subscriptions = {key: False for key in self._datastore.captures}
            else:
                self._subscriptions = {"f{}".format(i): False for i in range(tracks)}
                self._subscriptions["source"] = False
                map(self._datastore.create, self._subscriptions.keys())

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

            log.msg("[WampCaptureComponent] Registering Procedure: io.timbr.kernel.{}.captures.subscriptions".format(self._kernel_key))
            yield self.register(subscriptions, 'io.timbr.kernel.{}.captures.subscriptions'.format(self._kernel_key))

            def subscribe(key, structure_level=0):
                assert re.match("[_A-Za-z][_a-zA-Z0-9]*", key)
                assert not keyword.iskeyword(key)

                if key in self._subscriptions:
                    if self._subscriptions[key]:
                        return False
                    else:
                        self._subscriptions[key] = True
                        return True
                else:
                    self._datastore.create(key)
                    self._subscriptions[key] = True
                    return True


            log.msg("[WampCaptureComponent] Registering Procedure: io.timbr.kernel.{}.captures.subscribe".format(self._kernel_key))
            yield self.register(subscribe, 'io.timbr.kernel.{}.captures.subscribe'.format(self._kernel_key))

            def unsubscribe(key):
                if key in self._subscriptions and self._subscriptions[key]:
                    self._datastore.checkpoint(key)
                    self._subscriptions[key] = False

            log.msg("[WampCaptureComponent] Registering Procedure: io.timbr.kernel.{}.captures.unsubscribe".format(self._kernel_key))
            yield self.register(unsubscribe, 'io.timbr.kernel.{}.captures.unsubscribe'.format(self._kernel_key))

            def flag_endpoint(endpoint):
                dirty_keys = [key for key in self._subscriptions if self._conn._endpoint == endpoint]
                for key in dirty_keys:
                    self._datastore.checkpoint(key)
                if(len(dirty_keys) > 0):
                    return True
                else:
                    return False

            log.msg("[WampCaptureComponent] Registering Procedure: io.timbr.kernel.{}.captures.flag_endpoint".format(self._kernel_key))
            yield self.register(flag_endpoint, 'io.timbr.kernel.{}.captures.flag_endpoint'.format(self._kernel_key))

            @inlineCallbacks
            def captures():
                output = []
                for key in self._datastore.captures:
                    rec = {"key": key, "active": self._subscriptions[key]}
                    rec["segments"] = []
                    for segment in self._datastore.segments(key):
                        preview_item = yield preview(key, segment=segment)
                        rec["segments"].append({"name": segment, "rows": self._datastore.nrows(key, segment),
                                        "preview": preview_item})
                    output.append(rec)
                returnValue(output)

            log.msg("[WampCaptureComponent] Registering Procedure: io.timbr.kernel.{}.captures.captures".format(self._kernel_key))
            yield self.register(captures, 'io.timbr.kernel.{}.captures.captures'.format(self._kernel_key))

            @inlineCallbacks
            def preview(key, count=5, segment='current'):
                @inlineCallbacks
                def critical():
                    preview_items = yield self._datastore.fetch(key, segment, n=count)
                    log.msg("preview_items={}".format(preview_items))
                    returnValue([serializer.wamp_safe_loads(item.tostring()) for item in preview_items])

                result = yield self._iterlocks[key].run(critical)
                returnValue(result)

            log.msg("[WampCaptureComponent] Registering Procedure: io.timbr.kernel.{}.captures.preview".format(self._kernel_key))
            yield self.register(preview, 'io.timbr.kernel.{}.captures.preview'.format(self._kernel_key))

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

            log.msg("[WampCaptureComponent] Registering Procedure: io.timbr.kernel.{}.captures.counter".format(self._kernel_key))
            yield self.register(counter, 'io.timbr.kernel.{}.captures.counter'.format(self._kernel_key), RegisterOptions(details_arg='details'))

            @inlineCallbacks
            def stream(key, details=None):
                @inlineCallbacks
                def critical():
                    for rec in self._datastore.stream(key):
                        yield details.progress(serializer.wamp_safe_loads(rec.tostring()))
                    returnValue(None)

                yield self._iterlocks[key].run(cooperate(critical()).whenDone())
                returnValue(None)

            log.msg("[WampCaptureComponent] Registering Procedure: io.timbr.kernel.{}.captures.stream".format(self._kernel_key))
            yield self.register(stream, 'io.timbr.kernel.{}.captures.stream'.format(self._kernel_key), RegisterOptions(details_arg='details'))

            @inlineCallbacks
            def raw_stream(key, details=None):
                @inlineCallbacks
                def critical():
                    for rec in self._datastore.stream(key):
                        yield details.progress(rec.tostring() + '\n')
                    returnValue(None)

                yield self._iterlocks[key].run(cooperate(critical()).whenDone())
                returnValue(None)

            log.msg("[WampCaptureComponent] Registering Procedure: io.timbr.kernel.{}.captures.raw_stream".format(self._kernel_key))
            yield self.register(raw_stream, 'io.timbr.kernel.{}.captures.raw_stream'.format(self._kernel_key), RegisterOptions(details_arg='details'))

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

            log.msg("[WampCaptureComponent] Registering Procedure: io.timbr.kernel.{}.captures.snapshot".format(self._kernel_key))
            yield self.register(snapshot, 'io.timbr.kernel.{}.captures.snapshot'.format(self._kernel_key), RegisterOptions(details_arg='details'))

        def onLeave(self, details):
            self._flush()
            log.msg("[WampCaptureComponent] onLeave()")
            log.msg("details: %s" % str(details))
            reactor.callLater(0.25, _capture_runner.run, WampCaptureComponent, start_reactor=False)

        def onDisconnect(self):
            log.msg("[WampCaptureComponent] onDisconnect")

    return WampCaptureComponent(kernel_key)



def main():
    global _capture_runner

    log.startLogging(open("machine/log/captd.log", "w"))

    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true", help="Enable debug output.")
    parser.add_argument("--wamp-realm", default=u"jupyter", help='Router realm')
    parser.add_argument("--wamp-url", default=u"wss://juno.timbr.io/wamp/route", help="WAMP Websocket URL")
    parser.add_argument("--token", type=unicode, help="OAuth token to connect to router")
    parser.add_argument("--session-key", help="The kernel key that you want to register with")
    args = parser.parse_args()


    _capture_runner = ApplicationRunner(url=unicode(args.wamp_url), realm=unicode(args.wamp_realm),
                                        headers={"Authorization": "Bearer {}".format(args.token),
                                                    "X-Kernel-ID": args.session_key})


    log.msg("Connecting to router: %s" % args.wamp_url)
    log.msg("  Project Realm: %s" % (args.wamp_realm))

    _capture_runner.run(build_capture_component(args.session_key), start_reactor=False)

    reactor.run()


