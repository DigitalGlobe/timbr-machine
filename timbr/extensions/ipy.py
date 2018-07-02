from timbr.machine.display import Display
from timbr.machine.dashboard import Dashboard
from timbr.machine.editor import Editor
from timbr.machine.dispatcher import Dispatcher


class IPythonMachineMixin(object):
    def __init__(self):
        self.create_dispatcher()

    def display_status(self, interval=1):
        self._display = Display(self, interval=interval)

    def dashboard(self):
        self._dashboard = Dashboard(self)

    def create_dispatcher(self):
        if self.dispatcher is not None:
            self.dispatcher.comm.close()
        self.dispatcher = Dispatcher(self)

    def dispatch(self, msg):
        if self.dispatcher is not None:
            self.dispatcher.dispatch(msg)

    def editor(self):
        self._editor = Editor(self)


