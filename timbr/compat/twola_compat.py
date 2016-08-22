from __future__ import print_function
from timbr.machine import Machine 
from collections import OrderedDict
import yaml
import os
import shlex
import optparse
import imp

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

def generate_template(ntransforms):
    lines = []
    lines.append("from timbr.machine import Machine\nMACHINE=Machine()\nfrom {source[0]} import {source[1]}")
    lines.append("MACHINE.set_source({source[1]}())")
    for i in range(ntransforms):
        lines.append("from {f" + str(i) + "[0]} import {f" + str(i) + "[1]}")
        lines.append("MACHINE[" + str(i) + "] = {f" + str(i) + "[1]}")
    lines.append("MACHINE.start()")
    return "\n".join(lines)

def get_module_entrypoint(full_mod_path):
    assert(os.path.exists(full_mod_path))
    with open(full_mod_path) as f:
        f.readline()
        cmds = f.readline()
    args = shlex.split(cmds)
    return args[3].strip("()")
    
def generate_project_structure(project_path):
    ds = OrderedDict()
    with open(os.path.join(project_path, "topology.yaml")) as f:
        tree = yaml.load(f)
    pdata = _compile_forest(tree)[-1]
    # source data
    modfile, _, modname = shlex.split(pdata[0])
    entrypoint = get_module_entrypoint(modfile)
    ds["source"] = (modname, entrypoint)
    # transform data
    for ind, cmd in enumerate(pdata[1:]):
        modfile, _, modname = shlex.split(cmd)
        entrypoint = get_module_entrypoint(os.path.join(project_path, modfile))
        ds["f{}".format(ind)] = (modname, entrypoint)
    return ds