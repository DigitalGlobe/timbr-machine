from __future__ import print_function
from collections import OrderedDict, namedtuple
import yaml
import os
import shlex
import json
import shutil


twola_module = namedtuple("TwolaModule", ["modfile", "modname", "effect"])

def _compile_forest(x, stk=[]):
    nodes = []
    if x is None:
        return nodes
    elif isinstance(x, list):
        for item in x:
            nodes.extend(_compile_forest(item))
    elif isinstance(x, dict):
        for k in x:
            nodes.extend(_compile_forest(k))
            stk.append(k)
            nodes.extend(_compile_forest(x[k], stk))
            stk.pop()
    else:
        stk.append(x)
        nodes.append(tuple(stk))
        stk.pop()
    return nodes

def _get_module_effect(modfile):
    assert(os.path.exists(modfile))
    with open(modfile) as f:
        f.readline()
        cmds = f.readline()
    args = shlex.split(cmds)
    return args[3].strip("()")

def init_template(nfuncs):
    lines = ["from {0.modname} import {0.effect} as _source"]
    lines.extend(["from {" + str(i + 1) + ".modname} import {" + str(i + 1) + ".effect} as _f" + str(i) for i in range(nfuncs)])
    return "\n".join(lines)

def topology_to_data(yaml_path):
    with open(path) as f:
        tree = yaml_path.load(f)
    _data = _compile_forest(tree)[-1]
    ds = []
    for cmd in _data:
        modfile, _, modname = shlex.split(cmd)
        effect = _get_module_effect(modfile)
        ds.append(machine_effect(modfile, modname, effect))
    return ds

def machine_config(init_path, twola):
    ds = {"machine_init_path": init_path}
    ds["source"] = twola[0]._asdict()
    ds["transforms"] = []
    for fn in twola[1:]:
        ds["transforms"].append(fn._asdict())
    return ds

def convert_twola_project(project_path, target_path=None):
    assert os.path.isdir(project_path)
    twola = yaml_to_data(os.path.join(project_path, "topology.yaml"))
    if target_path is None:
        target_path = project_path
    else:
        for mod in twola:
            shutil.copy(os.path.join(project_path, mod.modfile), target_path)    
    # copy files 
    #write __init__.py
    init = init_template(len(twola) - 1)
    formatted = init.format(*twola)
    with open(os.path.join(target_path, "__init__.py"), "w") as f:
        f.write(formatted)
    # write machine datastructure
    ds = machine_config(os.path.join(target_path, "__init__.py"), twola)
    with open(os.path.join(target_path, "machine.json"), "w") as f:
        json.dump(ds)
