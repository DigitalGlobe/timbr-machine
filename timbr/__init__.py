from machine.component import handle_comm_opened

def load_ipython_extension(ip):
    """Set up IPython to work with widgets"""
    if not hasattr(ip, 'kernel'):
        return
    register_comm_target(ip.kernel)

def register_comm_target(kernel=None):
    """Register the jupyter.widget comm target"""
    if kernel is None:
        kernel = get_ipython().kernel
    kernel.comm_manager.register_target('timbr.machine', handle_comm_opened)

# deprecated alias
handle_kernel = register_comm_target

def _handle_ipython():
    """Register with the comm target at import if running in IPython"""
    ip = get_ipython()
    if ip is None:
        return
    load_ipython_extension(ip)

_handle_ipython()

def _jupyter_nbextension_paths():
    return [{
        'section': 'notebook',
        'src': 'static',
        'dest': 'timbr_machine',
        'require': 'timbr_machine/index'
    }]
