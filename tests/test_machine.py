import unittest
from mock import patch, Mock, MagicMock, create_autospec, call


class PatchMixin(object):
    """
    Testing utility mixin that provides methods to patch objects so that they
    will get unpatched automatically.
    """

    def patch(self, *args, **kwargs):
        patcher = patch(*args, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def patch_object(self, *args, **kwargs):
        patcher = patch.object(*args, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def patch_dict(self, *args, **kwargs):
        patcher = patch.dict(*args, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

class TestMachine(PatchMixin, unittest.TestCase):
	def setup(self):
		pass

	def test_Machine(self):
		pass

	def test_SourceConsumer(self):
		pass

	def test_MachineConsumer(self):
		pass
		

