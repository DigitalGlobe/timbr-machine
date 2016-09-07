from setuptools import setup
from setuptools.command.develop import develop as _develop
from setuptools.command.install import install as _install
import os

extension_dir = os.path.join(os.path.dirname(__file__), "timbr", "static")

class develop(_develop):
    try:
        from notebook.nbextensions import install_nbextension
        from notebook.services.config import ConfigManager
        def run(self):
            _develop.run(self)
            install_nbextension(extension_dir, symlink=True,
                                overwrite=True, user=True, destination="timbr_machine")
            cm = ConfigManager()
            cm.update('notebook', {"load_extensions": {"timbr_machine/index": True } })
    except:
        pass

class install(_install):
    try:
        from notebook.nbextensions import install_nbextension
        from notebook.services.config import ConfigManager
        def run(self):
            _install.run(self)
            cm = ConfigManager()
            cm.update('notebook', {"load_extensions": {"timbr_machine/index": True } })
    except:
        pass

setup(name='timbr-machine',
      cmdclass={'develop': develop, 'install': install},
      version='0.1',
      description='Dask-based data collection and processing machine',
      url='https://bitbucket.com/timbr-io/timbr-machine',
      author='Pramukta Kumar',
      author_email='pramukta.kumar@timbr.io',
      license='MIT',
      packages=['timbr', 'timbr.machine'],
      zip_safe=False,
      entry_points = {
        'console_scripts': [
            "machine-captd = twola.capture:main",
            ]
        },
      data_files=[
        ('share/jupyter/nbextensions/timbr_machine', [
            'timbr/static/index.js'
        ]),
      ],
      install_requires=[
          "pymongo>=2.8",
          "dask",
          "ipython",
          "observed",
          "jupyter_react",
          "subprocess32"
        ],
      tests_require=[
          "nose",
          "mock",
        ]
      )
