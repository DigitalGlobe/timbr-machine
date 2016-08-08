class MachineError(Exception):
    pass

class UpstreamError(MachineError):
    def __init__(self, fn):
        self.args = ["Task <{}> never ran due to upstream dask task error".format(fn)]