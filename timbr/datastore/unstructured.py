import abc
from bson.objectid import ObjectId


class AbstractUnstructuredStore(object):

    __metaclass__ = abc.ABCMeta

    @abc.abstractproperty
    def captures(self):
        """Returns a list containing the names of each CAPTURE registered with the STORE"""
        raise NotImplementedError

    @abc.abstractmethod
    def segments(self, key):
        """Returns a list of existing SEGMENTS associated with CAPTURE {str <key>} or None if key is not registered"""
        raise NotImplementedError

    @abc.abstractmethod
    def create(self, key, n=5):
        """Create a capture with a SEGMENT labelled 'current' available for writing"""
        raise NotImplementedError

    @abc.abstractmethod
    def delete(self, key, segment):
        """Attempts to delete SEGMENT {str <segment>} from CAPTURE {str <key>} """
        raise NotImplementedError

    @abc.abstractmethod
    def stream(self, key):
        """Returns a generator that iterates over database SEGMENT 'current' registered to CAPTURE 'key' and returns raw data records from oldest to newest"""
        raise NotImplementedError

    @abc.abstractmethod
    def flush(self, key=None):
        """Write any pending data to disk on SEGMENT 'current' registered to CAPTURE 'key'.  If key is None, flush all data """
        raise NotImplementedError

    @abc.abstractmethod
    def nrows(self, key, segment):
        """Returns the number of appended data records in {str <segment>} associated with CAPTURE {str <key>}"""
        raise NotImplementedError

    @abc.abstractmethod
    def rename(self, key, new_name):
        """Renames the SEGMENT 'current' associated with CAPTURE {str <key>} to {str <new name>}"""
        raise NotImplementedError

    @abc.abstractmethod
    def fetch(self, key, segment, n):
        raise NotImplementedError

    def _last_segment(self, key):
        _segments = self.segments(key)
        try:
            last_segment = [int(s[1:]) for s in _segments if s != "current"][-1]
        except IndexError, ie:
            last_segment = 0
        return last_segment

    def _next_segment(self, key):
        return "S" + str(self._last_segment(key) + 1)

    def checkpoint(self, key, n=5):
        assert key in self.captures, "Attempted to checkpoint non-existent capture: %s" % key
        # 1) Make sure all pending data has been written to disk
        self.flush(key)
        # 2) Compute the next segment
        next_segment = self._next_segment(key)
        # 3) Make sure there is something to checkpoint (ie the current key exists)
        if "current" not in self.segments(key):
            return "S" + str(self._last_segment(key))

        self.rename(key, next_segment)
        self.create(key) # create's a new current segment
        old_segments = [s for s in self.segments(key) if s != "current"][:-n]
        for segment in old_segments:
            self.delete(key, segment)

        return next_segment