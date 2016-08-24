from __future__ import print_function
from collections import OrderedDict, namedtuple
import yaml
import os
import shlex
import json


machine_effect = namedtuple("MachineEffect", ["module", "effect", "name"])

class TwolaProjectStore(object):
    def __init__(self, project_path):
        self.project_path = project_path
        with open(os.path.join(project_path, "topology.yaml")) as f:
            tree = yaml.load(f)
        self._data = self._compile_forest(tree)[-1]
        self._twola = self._twola_store()        

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
    def _get_module_effect(modfile):
        assert(os.path.exists(modfile))
        with open(modfile) as f:
            f.readline()
            cmds = f.readline()
        args = shlex.split(cmds)
        return args[3].strip("()")

    @property
    def init_template(self):
        lines = ["from {0.module} import {0.effect} as _source"]
        lines.extend(["from {" + str(i + 1) + ".module} import {" + str(i + 1) + ".effect} as _f" + str(i) for i in range(len(self._twola) - 1)])
        return "\n".join(lines)

    def _twola_store(self):
        ds = []
        for cmd in self._data:
            modfile, _, modname = shlex.split(cmd)
            effect = self._get_module_effect(modfile)
            ds.append(machine_effect(modname, effect, modname))
        return ds

    def machine_init(self):
        s = self.init_template
        return s.format(*self._twola)
 
    def machine_config(self):
        s = {"_module_path": self.project_path}
        s["source"] = self._twola[0]._asdict()
        s["transforms"] = []
        for fn in self._twola[1:]:
            s["transforms"].append(fn._asdict())
        return s

def configure_twola_project(project_path=None):
    if project_path is None:
        project_path = os.getcwd()
    tps = TwolaProjectStore(project_path)
    with open(os.path.join(project_path, "_machine_.py"), "w") as f:
        f.write(tps.machine_init())
    with open(os.path.join(project_path, "machine.json"), "w") as f:
        json.dump(tps.machine_config(), f)

