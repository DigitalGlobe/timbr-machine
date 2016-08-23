from __future__ import print_function
from collections import OrderedDict, namedtuple
import yaml
import os
import shlex


machine_effect = namedtuple("MachineEffect", ["module", "entrypoint", "name"])

class TwolaCompatibilityStructure(object):
    def __init__(self, project_path):
        self.project_path = project_path
        with open(os.path.join(project_path, "topology.yaml")) as f:
            tree = yaml.load(f)
        self._data = self._compile_forest(tree)[-1]
        self.twola = self._twola()        

    def _compile_forest(self, x, stk=[]):
        nodes = []
        if x is None:
            return nodes
        elif isinstance(x, list):
            for item in x:
                nodes.extend(self._compile_forest(item))
        elif isinstance(x, dict):
            for k in x:
                nodes.extend(self._compile_forest(k))
                stk.append(k)
                nodes.extend(self._compile_forest(x[k], stk))
                stk.pop()
        else:
            stk.append(x)
            nodes.append(tuple(stk))
            stk.pop()
        return nodes

    @staticmethod
    def _get_module_entrypoint(modfile):
        assert(os.path.exists(modfile))
        with open(modfile) as f:
            f.readline()
            cmds = f.readline()
        args = shlex.split(cmds)
        return args[3].strip("()")

    @property
    def init_template(self):
        lines = ["from {" + str(i) + ".module} import {" + str(i) + ".entrypoint}" for i in range(len(self.twola))]
        return "\n".join(lines)

    def _twola(self):
        ds = []
        for cmd in self._data:
            modfile, _, modname = shlex.split(cmd)
            entrypoint = self._get_module_entrypoint(modfile)
            ds.append(machine_effect(modname, entrypoint, modname))
        return ds

    def machine_init(self):
        s = self.init_template
        return s.format(*self.twola)
 
    def machine_config(self):
        s = {}
        s["source"] = self.twola[0]._asdict()
        s["transforms"] = {}
        for ind, fn in enumerate(self.twola[1:]):
            s["transforms"]["f{}".format(ind)] = fn._asdict()
        return s
