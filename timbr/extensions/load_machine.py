from timbr.machine import Machine
import os

def load_machine():
    """
    Loads a running machine into the jupyter namespace as MACHINE. If a loadable project exists, in /projects,
    we try to instantiate a machine from the config file there. Otherwise a new machine is instantiated and returned.
    """
    prj_path = os.environ.get('TIMBR_PROJECT', None)
    if prj_path is not None:
        if not os.path.exists(prj_path):
            os.makedirs(prj_path)
        if os.path.isfile(os.path.join(prj_path, 'machine.json')):
            config_file = os.path.join(prj_path, 'machine.json')
            init_file = os.path.join(prj_path, '__init__.py')
            MACHINE = Machine.from_json(config_file, init_path=init_file)
            MACHINE.start()
            return MACHINE
    MACHINE = Machine()
    MACHINE.start()
    return MACHINE

if __name__ == "__main__":
    MACHINE = load_machine()
