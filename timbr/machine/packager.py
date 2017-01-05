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

def build_packager_component(kernel_key, conda_env, env_path="/home/gremlin/anaconda/envs", pkg_path="/home/gremlin/environments"):
    class WampPackagerComponent(ApplicationSession):
        def __init__(self, kernel_key, conda_env=conda_env, env_path=env_path, pkg_path=pkg_path, config=ComponentConfig(realm=u"jupyter")):
            ApplicationSession.__init__(self, config=config)
            self._kernel_key = kernel_key
            self._conda_env = conda_env
            self._env_path = env_path
            self._pkg_path = pkg_path
            self._conda_env = conda_env
            self._lock = DeferredLock()

        @inlineCallbacks
        def install_pkg(self, pkg_type, pkg, details):
            if str(pkg_type) == 'pip':
                pipcmd = sh.Command(os.path.join([self._env_path, '{}/bin/pip'.format(self._conda_env)]))
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
                  pkg_filepath = os.path.join(self._pkg_path, "%s.yaml" % pkg_name)
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

            log.msg("[WampPackagerComponent] Registering Procedure: io.timbr.kernel.{}.pkgd.install_environment".format(self._kernel_key))
            yield self.register(install_environment, 'io.timbr.kernel.{}.pkgd.install_environment'.format(self._kernel_key), RegisterOptions(details_arg = 'details'))

            @inlineCallbacks
            def install_package(pkg_type, pkg_name, details=None):
                @inlineCallbacks
                def install():
                    yield self.install_pkg(pkg_type, pkg_name, details)

                yield self._lock.run(install)
                returnValue(None)

            log.msg("[WampPackagerComponent] Registering Procedure: io.timbr.kernel.{}.pkgd.install_package".format(self._kernel_key))
            yield self.register(install_package, 'io.timbr.kernel.{}.pkgd.install_package'.format(self._kernel_key), RegisterOptions(details_arg = 'details'))

            @inlineCallbacks
            def package_environment(pkg_name, details=None):
                @inlineCallbacks
                def package():
                    pkg_filepath = os.path.join(self._pkg_path, "%s.yaml" %(pkg_name))
                    yield cooperative_consume(
                        sh.conda("env", "export", "-n", self._conda_env, "--file", pkg_filepath, _iter_noblock=True), details.progress)
                    returnValue(None)

                yield self._lock.run(package)
                returnValue(None)

            log.msg("[WampPackagerComponent] Registering Procedure: io.timbr.kernel.{}.pkgd.package_environment".format(self._kernel_key))
            yield self.register(package_environment, 'io.timbr.kernel.{}.pkgd.package_environment'.format(self._kernel_key), RegisterOptions(details_arg = 'details'))

        def onLeave(self, details):
            log.msg("[WampPackagerComponent] onLeave()" )
            log.msg("details: %s" % str(details))
            reactor.callLater(0.25, _packager_runner.run, build_packager_component(self._kernel_key, self._conda_env), start_reactor=False)

        def onDisconnect(self):
            log.msg("[WampPackagerComponent] onDisconnect()")

    return WampPackagerComponent(kernel_key)


def main():
    global _packager_runner

    log.startLogging(sys.stdout)

    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true", help="Enable debug output.")
    parser.add_argument("-wamp-realm", default=u"jupyter", help="Router realm")
    parser.add_argument("--wamp-url", default=u"wss://juno.timbr.io/wamp/route", help="WAMP Websocket URL")
    parser.add_argument("--token", type=unicode, help="OAuth token to connect to router")
    parser.add_argument("--session-key", help="The kernel key that you want to register with")
    parser.add_argument("--env", default="juno", help="The target Anaconda install and package environment")
    args = parser.parse_args()


    _packager_runner = ApplicationRunner(url=unicode(args.wamp_url), realm=unicode(args.wamp_realm),
                                        headers={"Authorization": "Bearer {}".format(args.token),
                                                    "X-Kernel-ID": args.session_key})

    log.msg("Connecting to router: %s" % args.wamp_url)
    log.msg("  Project Realm: %s" % (args.wamp_realm))

    _packager_runner.run(build_packager_component(args.session_key, conda_env=args.env), start_reactor=False)

    reactor.run()

if __name__ == "__main__":
    main()
