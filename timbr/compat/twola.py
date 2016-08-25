from __future__ import print_function
from collections import OrderedDict, namedtuple
import yaml
import os
import shlex
import json
import shutil

from .util import copytree

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
    lines = ["from {0.modname} import {0.effect} as source"]
    lines.extend(["from {" + str(i + 1) + ".modname} import {" + str(i + 1) + ".effect} as f" + str(i) for i in range(nfuncs)])
    return "\n".join(lines)

def topology_to_data(path):
    with open(os.path.join(path, "topology.yaml")) as f:
        tree = yaml.load(f)
    _data = _compile_forest(tree)[-1]
    ds = []
    for cmd in _data:
        modfile, _, modname = shlex.split(cmd)
        effect = _get_module_effect(os.path.join(path, modfile))
        ds.append(twola_module(modfile, modname, effect))
    return ds

def machine_config(path, twola):
    package_path, package_name = os.path.split(path)
    ds = {"init": os.path.join(path, "__init__.py")}
    ds["source"] = ("source", {"name": twola[0].effect})
    ds["functions"] = []
    for ind, fn in enumerate(twola[1:]):
        ds["functions"].append(("f{}".format(ind), {"name": fn.effect}))
    return ds

def convert_project(project_path, target_path=None):
    assert os.path.isdir(project_path)
    twola = topology_to_data(project_path)
    if target_path is None or target_path == project_path:
        target_path = project_path
    else:
        if not os.path.isdir(target_path):
            os.mkdirs(target_path)
        copytree(project_path, target_path)  
    # copy files 
    #write __init__.py
    init = init_template(len(twola) - 1)
    formatted = init.format(*twola)
    with open(os.path.join(target_path, "__init__.py"), "w") as f:
        f.write(formatted)
    # write machine datastructure
    ds = machine_config(target_path, twola)
    with open(os.path.join(target_path, "machine.json"), "w") as f:
        json.dump(ds, f)
