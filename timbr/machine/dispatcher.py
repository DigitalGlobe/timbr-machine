from traitlets import Dict, observe
from jupyter_react import Component
from time import sleep

class Dispatcher(Component):
    """
      A generic component for dispatching messages over comms 
    """
    def __init__(self, module=None, **kwargs):
        super(Dispatcher, self).__init__(target_name='timbr.machine', **kwargs)
        self.on_msg(self._handle_msg)
        self._module = module

    def dispatch(self, msg):
        self.send({'method': 'dispatch', 'props': msg})
