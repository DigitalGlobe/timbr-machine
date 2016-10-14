from twisted.internet import reactor

import sys
import argparse
import os
import sh
import errno
import yaml

from types import StringType

from twisted.python import log
from twisted.internet.defer import inlineCallbacks, returnValue, DeferredLock
from twisted.internet.task import cooperate

from autobahn.wamp.types import RegisterOptions, ComponentConfig
from autobahn.twisted.wamp import ApplicationRunner, ApplicationSession
from autobahn.wamp.exception import ApplicationError

_packager_runner = None

def cooperative_consume(iter_noblock, cb):
    def fn():
        for e in iter_noblock:
            if e == errno.EWOULDBLOCK:
                yield
            else:
                yield cb(e)
    return cooperate(fn()).whenDone()

def build_packager_component(kernel_key):
    class WampPackagerComponent(ApplicationSession):
        def __init__(self, kernel_key, config=ComponentConfig(realm=u"jupyter"), base_path="/twola-data/environments", conda_env="topology-env"):
            ApplicationSession.__init__(self, config=config)
            self._kernel_key = kernel_key
            self._base_path = base_path
            self._conda_env = conda_env
            self._lock = DeferredLock()

        @inlineCallbacks
        def install_pkg(self, pkg_type, pkg, details):
            if str(pkg_type) == 'pip':
                pipcmd = sh.Command('/miniconda/envs/{}/bin/pip'.format(self._conda_env))
                yield cooperative_consume( pipcmd("install", pkg, _iter_noblock=True), details.progress)
            else:
                yield cooperative_consume( sh.conda("install", "--name", self._conda_env, pkg, "-y", _iter_noblock=True), details.progress)
            returnValue(None)

        @inlineCallbacks
        def onJoin(self, details):
            log.msg("[WampPackagerComponent] onJoin()")

            @inlineCallbacks
            def install_environment(pkg_name, details=None):

                @inlineCallbacks
                def install():
                  pkg_filepath = os.path.join(self._base_path, "%s.yaml" % pkg_name)
                  if not os.path.exists(pkg_filepath):
                      raise IOError("Package specification file :: %s :: not found" % pkg_filepath)
                  else:
                      with open(pkg_filepath) as env:
                        pkgs = yaml.load(env)

                        conda_deps = ["=".join(p.split("=")[:1]) for p in pkgs['dependencies'] if isinstance(p, StringType)]
                        if conda_deps:
                          yield self.install_pkg('conda', conda_deps, details)

                        pip_deps = [x for x in pkgs['dependencies'] if isinstance(x, dict) and 'pip' in x]
                        if pip_deps:
                            yield self.install_pkg('pip', pip_deps[0]['pip'], details)

                  returnValue(None)

                yield self._lock.run(install)
                returnValue(None)

            log.msg("[WampPackagerComponent] Registering Procedure: io.timbr.twola.pkgd.install_environment")
            yield self.register(install_environment, 'io.timbr.kernel.{}.pkgd.install_environment'.format(self._kernel_key), RegisterOptions(details_arg = 'details'))

            @inlineCallbacks
            def install_package(pkg_type, pkg_name, details=None):
                @inlineCallbacks
                def install():
                    yield self.install_pkg(pkg_type, pkg_name, details)

                yield self._lock.run(install)
                returnValue(None)

            log.msg("[WampPackagerComponent] Registering Procedure: io.timbr.twola.pkgd.install_package")
            yield self.register(install_package, 'io.timbr.kernel.{}.pkgd.install_package'.format(self._kernel_key), RegisterOptions(details_arg = 'details'))

            @inlineCallbacks
            def package_environment(pkg_name, details=None):

                @inlineCallbacks
                def package():
                    pkg_filepath = os.path.join(self._base_path, "%s.yaml" %(pkg_name))
                    yield cooperative_consume(
                        sh.conda("env", "export", "-n", self._conda_env, "--file", pkg_filepath, _iter_noblock=True), details.progress)
                    returnValue(None)

                yield self._lock.run(package)
                returnValue(None)

            log.msg("[WampPackagerComponent] Registering Procedure: io.timbr.twola.pkgd.package_environment")
            yield self.register(package_environment, 'io.timbr.kernel.{}.pkgd.package_environment'.format(self._kernel_key), RegisterOptions(details_arg = 'details'))

        def onLeave(self, details):
            log.msg("[WampPackagerComponent] onLeave()" )
            log.msg("details: %s" % str(details))
            reactor.callLater(0.25, _packager_runner.run, WampPackagerComponent, start_reactor=False)

        def onDisconnect(self):
            log.msg("[WampPackagerComponent] onDisconnect()")


def main():
    global _project_realm, _packager_runner
    log.startLogging(sys.stdout)

    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true", help="Enable debug output.")
    parser.add_argument("-r", "--realm", default="twola", help="Crossbar router realm for this project")
    parser.add_argument("-c", "--connect", default=u"127.0.0.1", help="Crossbar router host.")
    parser.add_argument("--port", default=9000, type=int, help="Crossbar router port for connecting the packager.")
    
    args = parser.parse_args()


    _packager_runner = ApplicationRunner(url=u"ws://%s:%i" % (args.connect, args.port), realm=unicode(args.realm),
        debug=args.debug, debug_wamp=args.debug, debug_app=args.debug)

    log.msg("Router: ws://%s:%i" % (args.connect, args.port))
    log.msg("  Project Realm: %s" % (args.realm))

    _packager_runner.run(WampPackagerComponent, start_reactor=False)

    reactor.run()

if __name__ == "__main__":
    main()