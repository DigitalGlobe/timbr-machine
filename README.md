# timbr-machine

_timbr-machine_ is a library that provides a persistent, reconfigurable, per-message data processing runtime environment that is designed to run inside an IPython kernel (though not a requirement) based on [Continuum.io's Dask]().  Once instantiated and started the machine processes input data according to a table of functions that the user can configure.  Results and intermediate values of the data processing are serialized to json and published on a ZeroMQ PUB/SUB endpoint so that they may be captured, reported, and/or processed further downstream.

_timbr-machine_ is designed to work with [wamp-magic](https://bitbucket.com/timbr-io/wamp-magic) for remote control. 

## Installation

## Creating a Machine

To create a machine just import and instantiate it in a Notebook cell, on a REPL, or in a script.  Then call `start()`.

```Python
from timbr.machine import Machine
MACHINE = Machine() # by default this supports up to 8 processing elements
MACHINE.start()
```

## Processing Data

We can get data onto the machine in 2 basic ways: manually putting messages onto it and letting it consume an iterator.

### The Manual Way

```Python
MACHINE.put(message)
```

The machine instance exposes a `put()` method that places any piece of data onto the processing queue.  This is useful in situations where data is being provided by a callback function, a webhook, or when fine grained control is required.

### The Automatic Way

```Python
MACHINE.source = g
```
Here, we set the source to either an iterable or generator interface, or a function that returns a generator. For instance, g could be any of the following:
*
```Python
# A function that returns a generator
def my_generator_function():
    yield "hello world"
MACHINE.source = my_generator 
```
*
```Python 
# A generator instance
my_generator = my_generator_function()
MACHINE.source = my_generator
```
*
```Python
# An iterable instance
my_iterable = [1,2,3]
MACHINE.source = my_iterable
```

## Configuring the Machine

The default 8-step machine provides 8 function slots for configuring it's behavior.  By default each of these slots are set to an `identity` function that just passes the message through.  At the most basic level you can think of these functions as steps in a pipeline.  So the final output of the function would be `output = f7(f6(f5(f4(f3(f2(f1(f0))))))))`, though of course the machine would output all of the intermediate stages as well.

### User-defined functions

With a function defined, imported, or otherwise available in the same context as the Machine instance, they can be used to transform the data pushed into the machine like so:

```Python
MACHINE[0] = lambda x: x**2 # set position 3 to a lambda expression
MACHINE[3] = str # use position 3 to convert the value to a string
MACHINE[2] = lambda x: list(xrange(x)) # not sure why I'm doing this
del MACHINE[2] # nevermind

```

This can be done at any point in time, whether the machine is running or not, whether or not the machine is consuming data or not.  In addition the machine can be tested against particular data simply by calling it like a function.  For example:

```Python
output = MACHINE(14)
```

This bypasses the serialization and ZeroMQ publishing stages and just returns the collection of input, intermediate, and final outputs.  This is great for testing.  However, since no serialization is done, if functions work on object references, the output objects will all have the same reference and thus the intermediate data will be suppressed.  To aid debugging these scenarios it can be called with the keyword parameter `include_serialized=True`.

### Non-pipeline structures

The underlying processign topology is a kind of fat pipeline, enabling more complex processing flows than a standard one.  Each function slot receives the outputs of all previous functions, in reverse order.  So for example `f4` is called with upto 5 arguments, ie `f4(f3, f2, f1, f0, in)`.  Therefore `f4` can choose to process the input message directly, creating a tree structure.  A user definied function can choose to process as few or as many arguments as it wants.
