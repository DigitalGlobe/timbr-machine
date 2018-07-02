import os

if os.environ.get("some_application_runtime_arg"):
    from timbr.extensions.load_machine import *


