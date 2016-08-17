from __future__ import print_function
from timbr.machine import Machine 
import collections
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
    
def machine_from_project(project_path):
    machine = Machine()
    topology_path = os.path.join(project_path, "topology.yaml")
    with open(topology_path) as f:
        tree = yaml.load(f)
    prefix_list = _compile_forest(tree)[-1]
    # first configure the machine:
    for ind, cmd in enumerate(prefix_list[1:]):
        args = shlex.split(cmd)
        f, entrypoint = args[0] # use a parser 
        f = os.path.join(project_path, f)
        assert os.path.exists(f)
        try:
            usereffect = imp.load_source("usereffect", f)
            exec "entrypoint = usereffect.%s" % entrypoint
            assert callable(entrypoint) # should be a function
            machine[ind] = entrypoint
        except Exception as e: # figure out what exceptions
            print "could not configure machine with function {} from module {}".format(usereffect, f)
            raise
    # set the source
    cmd = prefix_list[0]
    args = shlex.split(cmd)
    f, entrypoint = args[0], args[-1]
    f = os.path.join(project_path, f)
    assert os.path.exists(f)
    try:
        usereffect = imp.load_source("usereffect", f)
        exec "entrypoint = usereffect.%s" % entrypoint
        assert isinstance(usereffect, collections.Iterable)
        machine.set_source(entrypoint)
    except Exception as e:
        print "could not set machine source with iterable {} from module {}".format(usereffect, f)
        raise
    return machine