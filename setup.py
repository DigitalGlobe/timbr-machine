from setuptools import setup

setup(name='timbr-machine',
      version='0.1',
      description='Dask-based data collection and processing machine',
      url='https://bitbucket.com/timbr-io/timbr-machine',
      author='Pramukta Kumar',
      author_email='pramukta.kumar@timbr.io',
      license='MIT',
      packages=['timbr', 'timbr.machine'],
      zip_safe=False,
      install_requires=[
          "pymongo>=2.8",
          "dask",
          "ipython",
        ]
      tests_require=[
          "nose",
          "mock",
        ]
      )
