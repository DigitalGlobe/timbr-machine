from traitlets import Dict, observe
from jupyter_react import Component
from time import sleep

class Dashboard(Component):
    """
      A UI component for displaying status info in notebooks via react components
    """
    def __init__(self, machine, interval=1, module=None, **kwargs):
        super(Dashboard, self).__init__(target_name='timbr.machine', **kwargs)
        self.on_msg(self._handle_msg)
        self.machine = machine
        self._module = module
        self.send({"method": "display", "props": {"config": {'kernel': '57ed6a3cb9216d8366a4c8fc', 'init': 'foo', 'functions': [['f0', {'name': 'foo'}], ['f1', {'name': 'bar'}]], 'source': [ 'source', {'name': 'source'}]}}})

    def _handle_msg(self, msg):
        data = msg['content']['data']
        if data.get('method', None) == 'capture' and data['data']['action'] in ['start', 'stop']:
            method = getattr(self.machine, data['data']['action'])
            method()

    def update(self):
        self.send({'method': 'update', 'props': { 'status': 'foo' }})
