from traitlets import Dict, observe
from jupyter_react import Component
from time import sleep

from timbr.machine.util import StoppableThread

class Poller(StoppableThread):
    """ 
      Stoppable Poller used to call a callback at a set interval 
      allows ipython to continue executing updates to the status UI 
      while executing other cells
    """
    def __init__(self, callback, interval=1):
        super(Poller, self).__init__()
        self.callback = callback
        self.interval = interval

    def run(self):
        while not self.stopped():
            try:
                self.callback()
                sleep(self.interval)
            except StopIteration:
                break

class Display(Component):
    """ 
      A UI component for displaying status info in notebooks via react components
    """
    def __init__(self, machine, interval=1, module=None, **kwargs):
        super(Display, self).__init__(target_name='timbr.machine', **kwargs)
        self.on_msg(self._handle_msg)
        self.machine = machine
        self.interval = interval
        self._module = module
        self.send({"method": "display"})

        self.machine.stop.add_observer(self._update)
        self.machine.start.add_observer(self._update)
        self.start()

    def start(self):
        self._poller = Poller(self._update, self.interval)
        self._poller.start()
        self._polling = True
        
    def stop(self):
        self._poller.stop()
        self._polling = False
        self._update()

    def _update(self):
        self._status = self.machine.status
        self._status['running'] = self.machine.running
        self.send({'method': 'update', 'props': { 'status': self._status }})

    def _handle_msg(self, msg):
        data = msg['content']['data']
        if data.get('method', '') == 'toggle' and data['data']['action'] in ['start', 'stop']:
            method = getattr(self.machine, data['data']['action'])
            method()
