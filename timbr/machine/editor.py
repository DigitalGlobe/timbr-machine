from traitlets import Dict, observe
from jupyter_react import Component
from time import sleep

class Editor(Component):
    """
      A UI component for constructing pipelines
    """
    def __init__(self, machine, interval=1, module=None, **kwargs):
        super(Editor, self).__init__(target_name='timbr.machine', **kwargs)
        self.on_msg(self._handle_msg)
        self.machine = machine
        self._module = module
        self.send({"method": "display", "props": {"config": self.machine._config }})

    def _handle_msg(self, msg):
        data = msg['content']['data']
        if data.get('method', None) == 'capture' and data['data']['action'] in ['start', 'stop']:
            method = getattr(self.machine, data['data']['action'])
            method()
